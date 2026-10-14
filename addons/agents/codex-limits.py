#!/usr/bin/env python3
"""Fill in Codex's limits when Omarchy's collector couldn't.

omarchy-agent-usage-codex asks the Codex app-server for the account before
the limits, and gives each answer a few seconds; the account can take far
longer to come back, so the record is left without limits. This asks the
same app-server for the limits alone (they answer in under a second), with
the plan from the account notification it sends on start, and writes them
into the collector's record in the shape the collector uses. A record that
already has limits is left alone, and nothing is written if this fails too.

The app-server is started from the real codex binary when mise manages it:
mise's shim (or a wrapper calling `mise use`) adds seconds to each start.
"""

import json
import os
import select
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

RECORD = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "omarchy/agents/usage/codex.json"


def codex_binary():
  try:
    found = subprocess.run(["mise", "which", "codex"], capture_output=True, text=True, timeout=10).stdout.strip()
    if found and os.access(found, os.X_OK):
      return found
  except Exception:
    pass
  return shutil.which("codex")


# The collector's own labels, so the record reads the same either way.
def limit_window(window):
  if not isinstance(window, dict) or window.get("usedPercent") is None:
    return None
  mins = int(window.get("windowDurationMins") or 0)
  if mins == 10080:
    label = "Weekly (7-day)"
  elif mins and mins % 60 == 0:
    label = f"{mins // 60}h window"
  elif mins:
    label = f"{mins}m window"
  else:
    label = "Limit"
  reset = window.get("resetsAt")
  return {
    "label": label,
    "percent": float(window["usedPercent"]) / 100.0,
    "resetsAt": datetime.fromtimestamp(int(reset), timezone.utc).isoformat() if reset else "",
  }


def fetch(codex):
  proc = subprocess.Popen(
    [codex, "-s", "read-only", "-a", "on-request", "app-server"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
  )
  plan = ""

  def send(message):
    proc.stdin.write(json.dumps(message) + "\n")
    proc.stdin.flush()

  def reply(request_id, timeout):
    nonlocal plan
    deadline = time.time() + timeout
    while time.time() < deadline:
      ready, _, _ = select.select([proc.stdout], [], [], 0.25)
      if not ready:
        continue
      line = proc.stdout.readline()
      if not line:
        break
      try:
        message = json.loads(line)
      except ValueError:
        continue
      if message.get("method") == "account/updated":
        plan = (message.get("params") or {}).get("planType") or plan
      if message.get("id") == request_id:
        return message
    raise TimeoutError

  try:
    send({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "island-agents", "version": "1"}}})
    reply(1, 10)
    send({"method": "initialized", "params": {}})
    send({"id": 2, "method": "account/rateLimits/read", "params": {}})
    limits = (reply(2, 15).get("result") or {}).get("rateLimits") or {}
    windows = [limit_window(limits.get("primary")), limit_window(limits.get("secondary"))]
    return [w for w in windows if w], limits.get("planType") or plan
  finally:
    proc.kill()


def main():
  try:
    record = json.loads(RECORD.read_text())
  except Exception:
    return
  if record.get("limits"):
    return
  codex = codex_binary()
  if not codex:
    return
  try:
    limits, plan = fetch(codex)
  except Exception:
    return
  if not limits:
    return
  record["limits"] = limits
  record["usageStatusText"] = ""
  if plan and not record.get("tierLabel"):
    record["tierLabel"] = plan
  # Atomically, as the collector writes it, so a reader never sees half.
  fd, tmp = tempfile.mkstemp(dir=RECORD.parent, prefix=".codex.")
  with os.fdopen(fd, "w") as out:
    json.dump(record, out)
  os.chmod(tmp, 0o600)
  os.replace(tmp, RECORD)


if __name__ == "__main__":
  main()
