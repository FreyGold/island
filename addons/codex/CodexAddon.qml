import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io
import ".."

// Local Codex CLI session monitor. The helper reads only Codex's local session
// metadata and turn state. It sends desktop notifications for state changes.
Addon {
  id: codexAddon
  views: [{ name: "codex-sessions", width: 520, padding: 20, component: sessionsView }]

  Component {
    id: sessionsView
    CodexSessionsView { codex: codexAddon; active: codexAddon.host.view === "codex-sessions" }
  }

  property var sessions: []
  property bool dataAvailable: true
  property bool receivedSnapshot: false
  property var previousStates: ({})
  property bool resting: false

  function localPath(file) { return decodeURIComponent(String(Qt.resolvedUrl(file)).replace("file://", "")) }
  function needsAction(status) {
    return status === "needsAction" || status === "failed" || status === "interrupted"
  }
  function workspaceNumber(row) {
    var processes = row.pids || []
    var toplevels = Hyprland.toplevels.values
    for (var i = 0; i < toplevels.length; i++) {
      var toplevel = toplevels[i]
      var pid = Number(toplevel.lastIpcObject.pid || 0)
      if (pid > 0 && processes.indexOf(pid) !== -1 && toplevel.workspace)
        return Number(toplevel.workspace.id || 0)
    }
    return 0
  }
  function workspaceText(row) {
    var workspace = workspaceNumber(row)
    return workspace > 0 ? "Workspace " + workspace : "Workspace unavailable"
  }
  // The permission hook puts this session title after the workspace label in
  // its notification. Terminal titles carry that session title, unlike cwd:
  // several Codex sessions can share one working folder.
  function focusSession(context) {
    context = String(context || "")
    var match = null
    for (var i = 0; i < sessions.length; i++) {
      var candidate = sessions[i]
      if (context.indexOf(String(candidate.title || "")) !== -1) {
        match = candidate
        break
      }
    }
    if (!match) return false
    var toplevels = Hyprland.toplevels.values
    for (var j = 0; j < toplevels.length; j++) {
      var window = toplevels[j].lastIpcObject || ({})
      var title = String(window.title || "").toLowerCase()
      if (title.indexOf(String(match.title || "").toLowerCase()) !== -1) {
        var address = String(window.address || "")
        var workspace = Number((window.workspace || {}).id || 0)
        if (!address) continue
        // Focus alone does not always follow a window across workspaces with
        // the user's Hyprland rules. Switch first, then focus the exact
        // address rather than any terminal that has the same cwd.
        Quickshell.execDetached([
          "bash", "-c",
          'hyprctl dispatch workspace "$1"; hyprctl dispatch focuswindow "address:$2"',
          "codex-focus", String(workspace), address
        ])
        return true
      }
    }
    return false
  }
  function notificationSummary(row) {
    if (row.status === "finished") return "Codex finished"
    if (row.status === "failed") return "Codex failed"
    if (row.status === "interrupted") return "Codex stopped"
    return row.detail === "Reply required" ? "Codex needs your reply" : "Codex needs confirmation"
  }
  function notify(row) {
    var body = workspaceText(row) + " · " + String(row.title || "Codex session")
    Quickshell.execDetached(["notify-send", "-a", "Codex", "-u", "normal", "-t", "7000", notificationSummary(row), body])
  }
  function take(line) {
    var payload
    try { payload = JSON.parse(line) } catch (e) { return }
    var rows = Array.isArray(payload.sessions) ? payload.sessions : []
    var next = ({})
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i]
      var state = row.status + "|" + String(row.detail || "")
      var before = previousStates[row.id]
      // A pending request is important even if Island starts after Codex has
      // asked for it. Finished sessions only notify after a state change.
      if ((!receivedSnapshot && needsAction(row.status))
          || (receivedSnapshot && before !== state
            && (needsAction(row.status) || (row.status === "finished" && String(before).indexOf("working|") === 0))))
        notify(row)
      next[row.id] = state
    }
    previousStates = next
    sessions = rows
    dataAvailable = payload.available !== false
    receivedSnapshot = true
  }

  Timer { id: retry; interval: 5000; onTriggered: codexAddon.resting = false }
  Process {
    id: monitor
    running: !codexAddon.resting
    command: ["python3", codexAddon.localPath("codex-sessions.py")]
    stdout: SplitParser { onRead: function(line) { codexAddon.take(line) } }
    onExited: if (!codexAddon.resting) { codexAddon.resting = true; retry.restart() }
  }
}
