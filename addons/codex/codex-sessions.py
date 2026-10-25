#!/usr/bin/env python3
"""Print the active local Codex CLI sessions as JSON lines.

The reader uses Codex's local state databases in read-only mode. It reads
session names, working folders, and turn state. It does not read session logs
or message bodies.
"""

import glob
import json
import os
import sqlite3
import time
from pathlib import Path
from urllib.parse import quote


POLL_SECONDS = 2
FINISHED_GRACE_SECONDS = 5 * 60
WORKING_STALE_SECONDS = 30 * 60
ACTION_STALE_SECONDS = 2 * 60 * 60
ACTION_DETAILS = {
    "requestapproval": "Confirmation required",
    "waitingonapproval": "Confirmation required",
    "requestuserinput": "Reply required",
    "waitingonuserinput": "Reply required",
    "requiresaction": "Action required",
    "requires_action": "Action required",
}


def newest_database(codex_home, prefix):
    candidates = glob.glob(str(codex_home / (prefix + "_*.sqlite")))
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


def connect_read_only(path):
    uri = "file:" + quote(str(path)) + "?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=0.2)


def one_line(value, fallback):
    value = " ".join(str(value or "").split())
    return value or fallback


def action_in_value(value):
    """Return the current request label, if a turn is waiting for the user."""
    if isinstance(value, list):
        for item in value:
            detail = action_in_value(item)
            if detail:
                return detail
        return None
    if not isinstance(value, dict):
        return None
    for key, child in value.items():
        normalized = str(key).replace("_", "").replace("/", "").lower()
        if normalized in ACTION_DETAILS:
            return ACTION_DETAILS[normalized]
        if normalized in ("status", "method", "type"):
            state = str(child).replace("_", "").replace("/", "").lower()
            if state in ACTION_DETAILS:
                return ACTION_DETAILS[state]
            if state.endswith("requestapproval"):
                return ACTION_DETAILS["requestapproval"]
            if state.endswith("requestuserinput"):
                return ACTION_DETAILS["requestuserinput"]
        # Commands, output, and message content can contain these words. They
        # are intentionally not inspected for approval state.
        if normalized in ("command", "aggregatedoutput", "content", "text", "summary", "message", "arguments"):
            continue
        detail = action_in_value(child)
        if detail:
            return detail
    return None


def requested_action(history, thread_id, turn_id):
    try:
        rows = history.execute(
            """
            SELECT item_json
            FROM thread_items
            WHERE thread_id = ? AND turn_id = ?
            ORDER BY rollout_ordinal DESC
            """,
            (thread_id, turn_id),
        )
    except sqlite3.Error:
        return None
    for (raw,) in rows:
        try:
            detail = action_in_value(json.loads(raw))
            if detail:
                return detail
        except (TypeError, ValueError):
            pass
    return None


def process_thread_id(pid):
    """Get the Codex thread ID exposed by an active local Codex process."""
    try:
        values = Path("/proc") / str(pid) / "environ"
        for entry in values.read_bytes().split(b"\0"):
            if entry.startswith(b"CODEX_THREAD_ID="):
                return entry.partition(b"=")[2].decode("utf-8", "ignore")
    except (OSError, ValueError):
        pass
    return None


def parent_pid(pid):
    try:
        raw = (Path("/proc") / str(pid) / "stat").read_text()
        # The executable name may contain spaces or parentheses. Everything
        # after the final closing parenthesis starts with state then parent PID.
        fields = raw.rpartition(")")[2].split()
        return int(fields[1])
    except (OSError, ValueError, IndexError):
        return 0


def process_ancestors(pid):
    """Return the Codex process and its ancestors up to the terminal."""
    ancestors = []
    seen = set()
    while pid and pid not in seen:
        ancestors.append(pid)
        seen.add(pid)
        pid = parent_pid(pid)
    return ancestors


def process_cwd(pid):
    try:
        return os.path.realpath(os.readlink(Path("/proc") / str(pid) / "cwd"))
    except OSError:
        return ""


def process_ids_by_thread(session_cwds):
    """Map Codex threads to their terminal process chain.

    Codex exposes CODEX_THREAD_ID for its own worker processes. The terminal UI
    does not always keep that variable while it waits at its prompt. In that
    case, the terminal working folder identifies the session.
    """
    processes = {thread_id: [] for thread_id in session_cwds}
    threads_by_cwd = {}
    for thread_id, cwd in session_cwds.items():
        if cwd:
            threads_by_cwd.setdefault(os.path.realpath(cwd), []).append(thread_id)
    try:
        entries = os.scandir("/proc")
    except OSError:
        return processes
    with entries:
        for entry in entries:
            if not entry.name.isdigit():
                continue
            pid = int(entry.name)
            ancestors = None
            thread_id = process_thread_id(entry.name)
            if thread_id in processes:
                ancestors = process_ancestors(pid)
                for ancestor in ancestors:
                    if ancestor not in processes[thread_id]:
                        processes[thread_id].append(ancestor)

            for matching_thread in threads_by_cwd.get(process_cwd(pid), []):
                if ancestors is None:
                    ancestors = process_ancestors(pid)
                for ancestor in ancestors:
                    if ancestor not in processes[matching_thread]:
                        processes[matching_thread].append(ancestor)
    return processes


def read_sessions(state_path, history_path):
    now = int(time.time())
    state = connect_read_only(state_path)
    history = connect_read_only(history_path)
    try:
        metadata = {
            row[0]: {
                "title": one_line(row[1] or row[2] or row[3] or row[4], "Codex session"),
                "cwd": one_line(row[5], ""),
                "updatedAt": int(row[6] or 0),
            }
            for row in state.execute(
                """
                SELECT id, name, title, preview, agent_nickname, cwd, updated_at
                FROM threads
                WHERE archived = 0
                """
            )
        }
        latest_turns = history.execute(
            """
            WITH latest AS (
                SELECT thread_id, MAX(rollout_ordinal) AS rollout_ordinal
                FROM thread_turns
                GROUP BY thread_id
            )
            SELECT turns.thread_id, turns.turn_id, turns.status,
                   turns.started_at, turns.completed_at
            FROM thread_turns AS turns
            JOIN latest
              ON latest.thread_id = turns.thread_id
             AND latest.rollout_ordinal = turns.rollout_ordinal
            """
        )
        process_ids = process_ids_by_thread({thread_id: info["cwd"] for thread_id, info in metadata.items()})
        sessions = []
        for thread_id, turn_id, turn_status, started_at, completed_at in latest_turns:
            info = metadata.get(thread_id)
            if not info:
                continue
            turn_status = str(turn_status or "")
            updated_at = max(int(completed_at or started_at or 0), info["updatedAt"])
            if turn_status == "inProgress":
                action_detail = requested_action(history, thread_id, turn_id)
                status = "needsAction" if action_detail else "working"
                detail = action_detail or "Working"
                stale_after = ACTION_STALE_SECONDS if action_detail else WORKING_STALE_SECONDS
                if now - updated_at > stale_after:
                    continue
            elif turn_status == "completed":
                if now - updated_at > FINISHED_GRACE_SECONDS:
                    continue
                status = "finished"
                detail = "Finished"
            elif turn_status == "failed":
                if now - updated_at > FINISHED_GRACE_SECONDS:
                    continue
                status = "failed"
                detail = "Failed"
            elif turn_status == "interrupted":
                if now - updated_at > FINISHED_GRACE_SECONDS:
                    continue
                status = "interrupted"
                detail = "Stopped"
            else:
                continue
            sessions.append(
                {
                    "id": str(thread_id),
                    "title": info["title"],
                    "cwd": info["cwd"],
                    "status": status,
                    "detail": detail,
                    "pids": process_ids.get(str(thread_id), []),
                    "updatedAt": updated_at,
                }
            )
        order = {"needsAction": 0, "failed": 1, "interrupted": 2, "working": 3, "finished": 4}
        return sorted(sessions, key=lambda row: (order[row["status"]], -row["updatedAt"]))
    finally:
        state.close()
        history.close()


def snapshot():
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    state_path = newest_database(codex_home, "state")
    history_path = newest_database(codex_home, "thread_history")
    if not state_path or not history_path:
        return {"available": False, "sessions": []}
    try:
        return {"available": True, "sessions": read_sessions(state_path, history_path)}
    except (OSError, sqlite3.Error):
        return {"available": False, "sessions": []}


def main():
    while True:
        print(json.dumps(snapshot(), separators=(",", ":")), flush=True)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
