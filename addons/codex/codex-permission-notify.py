#!/usr/bin/env python3
"""Send an Island notification when local Codex asks for permission.

The script receives one Codex hook JSON object on standard input. It does not
write a hook decision, so Codex continues with its normal approval prompt.
"""

import glob
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote


MAX_DETAIL_LENGTH = 120


def one_line(value):
    return " ".join(str(value or "").split())


def shorten(value):
    value = one_line(value)
    if len(value) <= MAX_DETAIL_LENGTH:
        return value
    return value[: MAX_DETAIL_LENGTH - 1].rstrip() + "…"


def newest_state_database():
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    candidates = glob.glob(str(codex_home / "state_*.sqlite"))
    return max(candidates, key=os.path.getmtime) if candidates else None


def session_title(session_id):
    path = newest_state_database()
    if not path or not session_id:
        return "Codex session"
    try:
        uri = "file:" + quote(str(path)) + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=0.2) as database:
            row = database.execute(
                "SELECT name, title, preview, agent_nickname FROM threads WHERE id = ?",
                (session_id,),
            ).fetchone()
        if row:
            for value in row:
                value = one_line(value)
                if value:
                    return value
    except sqlite3.Error:
        pass
    return "Codex session"


def parent_pid(pid):
    try:
        fields = (Path("/proc") / str(pid) / "stat").read_text().rpartition(")")[2].split()
        return int(fields[1])
    except (OSError, ValueError, IndexError):
        return 0


def ancestor_pids():
    pids = []
    pid = os.getppid()
    while pid and pid not in pids:
        pids.append(pid)
        pid = parent_pid(pid)
    return pids


def workspace_number():
    try:
        clients = json.loads(subprocess.check_output(["hyprctl", "clients", "-j"], text=True, timeout=1))
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return 0
    pids = set(ancestor_pids())
    for client in clients:
        if int(client.get("pid") or 0) in pids:
            workspace = client.get("workspace") or {}
            return int(workspace.get("id") or 0)
    return 0


def request_detail(payload):
    tool = one_line(payload.get("tool_name")) or "action"
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}
    reason = shorten(tool_input.get("description"))
    if not reason:
        reason = shorten(tool_input.get("command"))
    if reason:
        return "Confirm " + tool + ": " + reason
    return "Confirm " + tool


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return
    workspace = workspace_number()
    location = "Workspace " + str(workspace) if workspace > 0 else "Workspace unavailable"
    title = session_title(one_line(payload.get("session_id")))
    body = location + " · " + title + "\n" + request_detail(payload)
    try:
        subprocess.run(
            ["notify-send", "-a", "Codex", "-u", "normal", "-t", "10000", "Codex needs confirmation", body],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        pass


if __name__ == "__main__":
    main()
