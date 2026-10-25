import QtQuick
import Quickshell
import Quickshell.Io

// VoxType publishes its state for every shortcut. The bridge adds live text.
Item {
  id: dictation
  readonly property string directory: Quickshell.env("XDG_RUNTIME_DIR") + "/voxtype"
  property string nativePhase: "idle"
  property string bridgePhase: "idle"
  property bool stopping: false
  readonly property bool capturing: nativePhase === "recording" || nativePhase === "streaming"
  readonly property string phase: capturing ? (stopping ? "transcribing" : "recording")
    : nativePhase === "transcribing" ? "transcribing"
    : bridgePhase === "done" || bridgePhase === "error" ? bridgePhase : "idle"
  property string transcript: ""
  property string error: ""
  property real startedAt: 0
  property real now: Date.now()
  readonly property bool active: phase !== "idle"
  readonly property bool recording: phase === "recording" || phase === "streaming"
  readonly property string timeText: {
    var seconds = Math.max(0, Math.floor((now - startedAt) / 1000))
    return Math.floor(seconds / 60) + ":" + String(seconds % 60).padStart(2, "0")
  }

  onCapturingChanged: {
    if (!capturing) return
    stopping = false
    transcript = ""
    error = ""
    startedAt = Date.now()
  }

  Process {
    id: status
    command: ["omarchy-voxtype-status"]
    running: true
    stdout: SplitParser {
      onRead: function(line) {
        try { dictation.nativePhase = String(JSON.parse(line).alt || "idle") } catch (e) {}
      }
    }
    onExited: { dictation.nativePhase = "idle"; retry.restart() }
  }
  Timer {
    id: retry
    interval: 5000
    onTriggered: status.running = true
  }

  FileView {
    path: dictation.directory + "/island-dictation.json"
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: {
      try {
        var value = JSON.parse(text())
        dictation.bridgePhase = String(value.phase || "idle")
        dictation.transcript = String(value.text || "")
        dictation.error = String(value.error || "")
        dictation.startedAt = Number(value.startedAt || Date.now())
      } catch (e) {}
    }
    onLoadFailed: dictation.bridgePhase = "idle"
  }

  Timer {
    interval: 1000
    repeat: true
    running: dictation.recording
    onTriggered: dictation.now = Date.now()
  }
  onStartedAtChanged: now = Date.now()

  function stop() {
    if (!recording) return
    stopping = true
    Quickshell.execDetached(["voxtype", "record", "stop"])
  }
}
