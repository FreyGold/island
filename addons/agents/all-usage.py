#!/usr/bin/env python3
"""Tokens for every model on this machine, for the Agents pane's All Models.

Omarchy's collectors keep one record per subscription in
~/.local/state/omarchy/agents/usage/ (Claude Code, Codex, ...), and count only
the opencode and pi sessions that ran on that subscription's provider. This
merges those records with the sessions they leave out, any other provider's
in opencode's database and pi's session files, into one record of the same
shape (recentDays for the last six days and today), plus `models`: each
model's name, where it ran, and its all-time tokens, largest first. It's
written to the island's cache, out of the collectors' folder so the stock
panel doesn't take it for an agent, and printed.
"""

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME = Path.home()
STATE = Path(os.environ.get("XDG_STATE_HOME") or HOME / ".local/state")
DATA = Path(os.environ.get("XDG_DATA_HOME") or HOME / ".local/share")
CACHE = Path(os.environ.get("XDG_CACHE_HOME") or HOME / ".cache")
RECORDS = STATE / "omarchy/agents/usage"
OUT = CACHE / "guilhermerisu.island/agents/all.json"

# Providers the collectors already count, per source.
COUNTED = {"opencode": {"anthropic", "openai"}, "pi": {"anthropic", "openai-codex"}}

now = datetime.now()
recent_dates = [(now - timedelta(days=offset)).strftime("%Y-%m-%d") for offset in range(6, -1, -1)]
recent = {day: 0 for day in recent_dates}
models = {}


def number(value):
  try:
    return int(value or 0)
  except (TypeError, ValueError):
    return 0


def local_day(value):
  try:
    if isinstance(value, (int, float)):
      stamp = datetime.fromtimestamp(value / 1000 if value > 1e11 else value)
    else:
      stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone()
    return stamp.strftime("%Y-%m-%d")
  except Exception:
    return ""


# "tencent/hy3-preview:free" → "Hy3 Preview (Free)", "big-pickle" → "Big Pickle".
def pretty(model):
  name, _, tag = str(model).rstrip("/").split("/")[-1].partition(":")
  words = [w if any(c.isdigit() for c in w) and len(w) > 1 else w.capitalize() for w in name.replace("_", "-").split("-") if w]
  return " ".join(words) + (f" ({tag.capitalize()})" if tag else "")


def provider_name(provider):
  return {"openrouter": "OpenRouter", "opencode": "Zen"}.get(provider, provider.replace("-", " ").title())


def add(key, name, source, tokens, day):
  entry = models.setdefault(key, {"id": key, "name": name, "source": source, "tokens": 0})
  entry["tokens"] += tokens
  if day in recent:
    recent[day] += tokens


def from_records():
  for path in sorted(RECORDS.glob("*.json")):
    try:
      record = json.loads(path.read_text())
    except Exception:
      continue
    if not record.get("hasLocalStats"):
      continue
    source = record.get("name") or record.get("id") or path.stem
    for day in record.get("recentDays") or []:
      if day.get("date") in recent:
        recent[day["date"]] += number(day.get("messageCount"))
    for model, usage in (record.get("modelUsage") or {}).items():
      tokens = sum(number(usage.get(k)) for k in ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens"))
      key = record.get("id", path.stem) + ":" + model
      entry = models.setdefault(key, {"id": model, "name": "", "source": source, "tokens": 0})
      entry["tokens"] += tokens


def from_opencode():
  db = DATA / "opencode/opencode.db"
  if not db.is_file():
    return
  try:
    conn = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
  except sqlite3.Error:
    return
  try:
    rows = conn.execute(
      "SELECT data FROM message WHERE data LIKE '%\"role\"%:%\"assistant\"%'"
      " AND CASE WHEN json_valid(data) THEN json_extract(data, '$.role') END = 'assistant'"
    )
    for (raw,) in rows:
      try:
        entry = json.loads(raw)
        provider = str(entry.get("providerID") or "")
        if provider in COUNTED["opencode"]:
          continue
        t = entry.get("tokens") or {}
        cache = t.get("cache") or {}
        tokens = number(t.get("input")) + number(t.get("output")) + number(t.get("reasoning")) + number(cache.get("read")) + number(cache.get("write"))
        if not tokens:
          continue
        model = str(entry.get("modelID") or "unknown")
        add("opencode:" + provider + "/" + model, pretty(model), "OpenCode · " + provider_name(provider), tokens,
            local_day((entry.get("time") or {}).get("created")))
      except Exception:
        continue
  except sqlite3.Error:
    pass
  finally:
    conn.close()


def from_pi():
  for root in (HOME / ".pi/agent/sessions", HOME / ".omp/agent/sessions"):
    if not root.exists():
      continue
    for path in root.rglob("*.jsonl"):
      seen = set()
      try:
        lines = path.open(errors="replace")
      except OSError:
        continue
      with lines:
        for line in lines:
          if '"usage"' not in line:
            continue
          try:
            entry = json.loads(line)
          except ValueError:
            continue
          message = entry.get("message") or {}
          if entry.get("type") != "message" or message.get("role") != "assistant" or entry.get("id") in seen:
            continue
          seen.add(entry.get("id"))
          provider = str(message.get("provider") or "")
          if provider in COUNTED["pi"] or str(message.get("api") or "").startswith("openai-codex"):
            continue
          u = message.get("usage") or {}
          tokens = number(u.get("input")) + number(u.get("output")) + number(u.get("cacheRead")) + number(u.get("cacheWrite")) or number(u.get("totalTokens"))
          if not tokens:
            continue
          model = str(message.get("model") or "unknown")
          add("pi:" + provider + "/" + model, pretty(model), "Pi · " + provider_name(provider), tokens,
              local_day(entry.get("timestamp") or message.get("timestamp")))


def main():
  from_records()
  from_opencode()
  from_pi()
  today = recent_dates[-1]
  record = {
    "id": "all",
    "name": "All Models",
    "updatedAt": datetime.now(timezone.utc).isoformat(),
    "hasLocalStats": True,
    "limits": [],
    "recentDays": [{"date": day, "messageCount": recent[day]} for day in recent_dates],
    "todayTotalTokens": recent[today],
    "sources": sorted({m["source"].split(" · ")[0] for m in models.values() if m["tokens"] > 0}),
    "models": sorted((m for m in models.values() if m["tokens"] > 0), key=lambda m: -m["tokens"]),
  }
  OUT.parent.mkdir(parents=True, exist_ok=True)
  fd, tmp = tempfile.mkstemp(dir=OUT.parent, prefix=".all.")
  with os.fdopen(fd, "w") as out:
    json.dump(record, out)
  os.replace(tmp, OUT)


if __name__ == "__main__":
  main()
