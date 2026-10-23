#!/bin/bash
# Acts on a call's window for the Meetings addon:
#   call.sh <class regex> <title regex or ""> focus
#   call.sh <class regex> <title regex or ""> key <mods> <key>
#   call.sh <class regex> <title regex or ""> focus-key <mods> <key>
# The window is the most recently focused mapped one whose class (and
# title, when given) match. A key goes to that window without focusing it
# (focus-key brings it forward first, for a key that opens something to
# use there), pressed and released apart: Hyprland's send_shortcut can leave a
# synthetic key stuck. Exits 1 when no window matches.
class="$1" title="$2" action="$3"

addr=$(hyprctl clients -j | jq -r --arg c "$class" --arg t "$title" '
  [.[] | select(.mapped and (.class | test($c; "i")) and ($t == "" or (.title | test($t))))]
  | sort_by(.focusHistoryID) | .[0].address // empty')
[ -n "$addr" ] || exit 1

case "$action" in
  focus)
    hyprctl dispatch "hl.dsp.focus({ window = \"address:$addr\" })" >/dev/null
    ;;
  key|focus-key)
    if [ "$action" = focus-key ]; then
      hyprctl dispatch "hl.dsp.focus({ window = \"address:$addr\" })" >/dev/null
      sleep 0.15
    fi
    for state in down up; do
      hyprctl dispatch "hl.dsp.send_key_state({ mods = \"$4\", key = \"$5\", state = \"$state\", window = \"address:$addr\" })" >/dev/null
      sleep 0.05
    done
    ;;
esac
