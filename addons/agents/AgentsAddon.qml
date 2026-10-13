import QtQuick
import Quickshell.Io
import ".."

// Agents: Claude Code's or Codex's usage as a pane in Settings (see
// AgentsPage), the agent picked in the addon's options. The figures are
// Omarchy's own: its omarchy-agent-usage-<agent> collectors write one record
// per agent into ~/.local/state/omarchy/agents/usage/, the same ones the stock
// Agents bar panel reads. The record is read as soon as Settings opens, and
// regenerated then and every few minutes while it stays open; the collectors
// reuse their recent transcript scans, so only the limits go over the wire.
Addon {
  id: agents
  settingsPages: [{
    title: "Agents",
    source: Qt.resolvedUrl("AgentsPage.qml"), properties: { agents: agents },
    about: "Usage limits and tokens by day for your coding agent.",
    search: "agents ai claude code codex usage limits rate session 5-hour five hour weekly week tokens day plan subscription"
  }]

  readonly property var providers: ({
    claude: { id: "claude", name: "Claude Code", glyph: "", color: "#d97757", login: "claude auth login" },
    codex: { id: "codex", name: "Codex", glyph: "", color: "#0a84ff", login: "codex login" }
  })
  readonly property var provider: providers[addon.option("agent")] || providers.claude

  readonly property bool watching: host.view === "settings"
  readonly property string usageDir: host.home + "/.local/state/omarchy/agents/usage"

  // The latest record for the picked agent, or null before one is read.
  property var record: null
  property bool updating: false
  onProviderChanged: { record = null; recordFile.reload(); refresh() }
  onWatchingChanged: if (watching) { recordFile.reload(); refresh() }

  FileView {
    id: recordFile
    path: agents.usageDir + "/" + agents.provider.id + ".json"
    watchChanges: true
    printErrors: false
    onLoaded: {
      try { agents.record = JSON.parse(text()) } catch (e) {}
    }
    onFileChanged: reload()
  }

  // A run collapses into one queued rerun if asked again meanwhile.
  property bool rerun: false
  Process {
    id: update
    onExited: {
      agents.updating = false
      recordFile.reload()
      if (agents.rerun) { agents.rerun = false; agents.refresh() }
    }
    stderr: StdioCollector {
      onStreamFinished: if (text.trim() !== "") console.warn("agents addon:", text.trim())
    }
  }
  function refresh() {
    if (update.running) { rerun = true; return }
    updating = true
    update.command = ["omarchy-agent-usage-update", provider.id]
    update.running = true
  }
  Timer {
    interval: 5 * 60 * 1000
    repeat: true
    running: agents.watching
    onTriggered: agents.refresh()
  }
}
