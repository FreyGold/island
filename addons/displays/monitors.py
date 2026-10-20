#!/usr/bin/env python3
"""The Displays addon's link to ~/.config/hypr/monitors.lua.

  monitors.py lua  <file> <json>   the hl.monitor calls that apply <json>,
                                   each keeping the extra fields its line
                                   in <file> has (vrr, bitdepth, …)
  monitors.py save <file> <json>   rewrite those lines in <file> (through its
                                   symlink, after a .bak), adding a line for
                                   any monitor that has none

<json> is a list of { output, mode, position, scale, transform, disabled }.
The rest of the file is left as it is. A missing file is not an error: `lua`
then applies the plain fields, and `save` does nothing.
"""
import json
import os
import shutil
import sys

# The fields the addon sets; any others on a line are kept.
OWNED = ("mode", "position", "scale", "transform", "disabled", "bitdepth", "cm", "sdrbrightness", "sdrsaturation")


def scan_value(text, i):
    """The end of the Lua value starting at text[i] (a string, a table, or a
    bare word or number)."""
    if text[i] in "\"'":
        quote, i = text[i], i + 1
        while i < len(text) and text[i] != quote:
            i += 2 if text[i] == "\\" else 1
        return i + 1
    depth = 0
    while i < len(text):
        c = text[i]
        if c in "\"'":
            i = scan_value(text, i)
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            if depth == 0:
                return i
            depth -= 1
        elif c == "," and depth == 0:
            return i
        i += 1
    return i


def table_end(text, i):
    """The index of the } closing the table whose body starts at text[i]."""
    depth = 0
    while i < len(text):
        c = text[i]
        if c in "\"'":
            i = scan_value(text, i)
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            if depth == 0:
                return i
            depth -= 1
        i += 1
    return i


def parse_table(body):
    """[(key, raw value)] of a flat `key = value, …` table body."""
    fields, i = [], 0
    while i < len(body):
        while i < len(body) and body[i] in " \t\r\n,":
            i += 1
        if i >= len(body):
            break
        eq = body.find("=", i)
        if eq < 0:
            break
        key = body[i:eq].strip()
        start = eq + 1
        while start < len(body) and body[start] in " \t":
            start += 1
        end = scan_value(body, start)
        fields.append((key, body[start:end].strip()))
        i = end
    return fields


def lua_string(raw):
    if len(raw) >= 2 and raw[0] in "\"'" and raw[-1] == raw[0]:
        return raw[1:-1]
    return None


def calls(text):
    """Every live `hl.monitor({ … })` call: (start, end, fields), skipping
    ones in -- comments."""
    found, i = [], 0
    while True:
        i = text.find("hl.monitor(", i)
        if i < 0:
            return found
        line_start = text.rfind("\n", 0, i) + 1
        if "--" in text[line_start:i]:
            i += 1
            continue
        brace = text.find("{", i)
        if brace < 0:
            return found
        close = table_end(text, brace + 1)
        end = text.find(")", close)
        if close >= len(text) or end < 0:
            return found
        found.append((i, end + 1, parse_table(text[brace + 1:close])))
        i = end + 1


def number(value):
    text = ("%.6f" % value).rstrip("0").rstrip(".")
    return text or "0"


def render(monitor, extra, live=False):
    fields = [("output", json.dumps(monitor["output"]))]
    # A monitor turned off keeps its mode for when it's back on.
    fields.append(("mode", json.dumps(monitor["mode"])))
    fields.append(("position", json.dumps(monitor["position"])))
    fields.append(("scale", number(monitor["scale"])))
    if monitor.get("transform"):
        fields.append(("transform", str(int(monitor["transform"]))))
    # Live, a monitor back on says so: Hyprland keeps an earlier
    # `disabled = true` otherwise.
    if monitor.get("disabled"):
        fields.append(("disabled", "true"))
    elif live:
        fields.append(("disabled", "false"))
    # Colour. Live, every field is sent, since Hyprland keeps a field an
    # earlier call set; saved, only what differs from Hyprland's defaults
    # (8 bits, sRGB, SDR at 1).
    if "cm" in monitor:
        hdr = str(monitor["cm"]).startswith("hdr")
        if live or monitor.get("bitdepth") == 10:
            fields.append(("bitdepth", str(int(monitor.get("bitdepth") or 8))))
        if live or monitor["cm"] != "srgb":
            fields.append(("cm", json.dumps(monitor["cm"])))
        for key in ("sdrbrightness", "sdrsaturation"):
            value = float(monitor.get(key, 1))
            if live or hdr or abs(value - 1) > 1e-6:
                fields.append((key, number(value)))
    fields += extra
    return "hl.monitor({ " + ", ".join("%s = %s" % f for f in fields) + " })"


def own_calls(text, name):
    return [c for c in calls(text) if lua_string(dict(c[2]).get("output", "")) == name]


def extras(text, name):
    found = own_calls(text, name)
    if not found:
        return []
    return [(k, v) for k, v in found[-1][2] if k != "output" and k not in OWNED]


def main():
    command, path, wanted = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
    real = os.path.realpath(path)
    text = open(real).read() if os.path.exists(real) else None

    if command == "lua":
        print("\n".join(render(m, extras(text or "", m["output"]), live=True) for m in wanted))
        return
    if command != "save" or text is None:
        return

    # Each monitor's last line is rewritten (Hyprland takes the last rule
    # for an output); a monitor with none gets one after the last call.
    edits, added = [], []
    for monitor in wanted:
        found = own_calls(text, monitor["output"])
        line = render(monitor, extras(text, monitor["output"]))
        if found:
            start, end, _ = found[-1]
            edits.append((start, end, line))
        else:
            added.append(line)
    for start, end, line in sorted(edits, reverse=True):
        text = text[:start] + line + text[end:]
    if added:
        every = calls(text)
        at = text.find("\n", every[-1][1]) if every else len(text)
        at = len(text) if at < 0 else at
        text = text[:at] + ("\n" if every or not text.endswith("\n") else "") + "\n".join(added) + text[at:]
        if not text.endswith("\n"):
            text += "\n"

    shutil.copy2(real, real + ".bak")
    tmp = real + ".tmp"
    with open(tmp, "w") as out:
        out.write(text)
    shutil.copymode(real, tmp)
    os.replace(tmp, real)


if __name__ == "__main__":
    main()
