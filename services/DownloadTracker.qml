import QtQuick
import Qt.labs.folderlistmodel
import Quickshell
import Quickshell.Io

// Downloads in progress, for the download live activity. Browsers (and
// yt-dlp) write to a temporary file (.part, .crdownload) in the Downloads
// folder and rename it when it's done. Firefox-based browsers (Zen, Firefox,
// LibreWolf) also list their downloads in progress, with the final name and
// size, in the profile's downloads.json, which gives progress and time left;
// for the rest this reports bytes so far and speed. The folder is only polled
// while something is downloading.
Item {
  id: tracker
  property bool enabled: true
  property string folder: Quickshell.env("HOME") + "/Downloads"

  // [{ name, part, bytes, speed, total }] for each download in progress
  // (total 0 when unknown).
  property var items: []
  // Also while a file that just vanished is checked under its final name,
  // so the pill doesn't blink before the finished card.
  readonly property bool active: enabled && (items.length > 0 || pendingFinals.length > 0)
  readonly property real speed: items.reduce(function(sum, d) { return sum + d.speed }, 0)
  readonly property real bytes: items.reduce(function(sum, d) { return sum + d.bytes }, 0)
  readonly property bool sized: items.length > 0 && items.every(function(d) { return d.total > 0 })
  // 0 to 1, or -1 when a size is unknown.
  readonly property real progress: sized
    ? Math.min(1, bytes / items.reduce(function(sum, d) { return sum + d.total }, 0)) : -1
  // Seconds, or -1 when unknown.
  readonly property real timeLeft: sized && speed > 0
    ? items.reduce(function(sum, d) { return sum + Math.max(0, d.total - d.bytes) }, 0) / speed : -1
  // True in a download's first seconds while its size may still come:
  // Firefox writes downloads.json a moment after a download starts.
  property bool awaitingSize: false
  // The download that just finished, for a few seconds.
  property string finishedName: ""
  property real finishedBytes: 0
  readonly property string finishedPath: finishedName ? folder + "/" + finishedName : ""
  // Its type's icon name (application/zip → application-zip).
  property string finishedIcon: ""
  onFinishedPathChanged: {
    finishedIcon = ""
    if (!finishedPath) return
    mimeQuery.command = ["xdg-mime", "query", "filetype", finishedPath]
    mimeQuery.running = true
  }
  Process {
    id: mimeQuery
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: tracker.finishedIcon = String(text || "").trim().replace("/", "-")
    }
  }

  property var previous: ({})
  property var lastBytes: ({})
  property var pendingFinals: []
  // Each temporary file's final name and size, from downloads.json, kept
  // after the browser drops it from there: { part: { name, total } }.
  property var known: ({})

  Process {
    running: true
    command: ["xdg-user-dir", "DOWNLOAD"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: { var dir = String(text || "").trim(); if (dir) tracker.folder = dir }
    }
  }

  FolderListModel {
    id: partials
    folder: "file://" + tracker.folder
    nameFilters: ["*.part", "*.crdownload"]
    showDirs: false
    showHidden: true
    onCountChanged: if (tracker.enabled) tracker.poll()
  }

  Timer {
    interval: 1000
    repeat: true
    running: tracker.enabled && (partials.count > 0 || tracker.pendingFinals.length > 0 || tracker.items.length > 0)
    onTriggered: tracker.poll()
  }

  // Lists each temporary file with its size ("P"), and which of the files
  // that just disappeared now exist under their final name ("D"), and each
  // Firefox-based profile's downloads.json ("J").
  Process {
    id: scan
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: tracker.apply(String(text || ""))
    }
  }
  function poll() {
    if (scan.running) return
    scan.command = ["sh", "-c",
      'cd "$1" || exit 0; shift; '
      + 'for f in *.part *.crdownload; do [ -f "$f" ] && printf "P\\t%s\\t%s\\n" "$(stat -c %s -- "$f")" "$f"; done; '
      + 'for f; do [ -s "$f" ] && printf "D\\t%s\\n" "$f"; done; '
      + 'for j in "$HOME"/.config/zen/*/downloads.json "$HOME"/.zen/*/downloads.json '
      + '"$HOME"/.mozilla/firefox/*/downloads.json "$HOME"/.config/mozilla/firefox/*/downloads.json '
      + '"$HOME"/.librewolf/*/downloads.json; do [ -f "$j" ] && printf "J\\t%s\\n" "$(tr -d "\\n" < "$j")"; done',
      "sh", folder].concat(pendingFinals)
    scan.running = true
  }

  function finalName(part) {
    return known[part] ? known[part].name : part.replace(/\.(part|crdownload)$/, "")
  }
  function baseName(path) { return String(path || "").replace(/^.*\//, "") }
  function learn(json) {
    var list = []
    try { list = JSON.parse(json).list || [] } catch (e) { return }
    list.forEach(function(d) {
      var t = d.target || {}
      if (!t.partFilePath || !t.path || t.partFilePath.replace(/\/[^/]*$/, "") !== folder) return
      known[baseName(t.partFilePath)] = { name: baseName(t.path), total: Number(d.totalBytes) || 0 }
    })
  }

  function apply(output) {
    var now = Date.now()
    var current = {}, rows = [], done = [], waiting = false
    output.split("\n").forEach(function(line) {
      var cols = line.split("\t")
      if (cols[0] === "P" && cols.length >= 3) current[cols.slice(2).join("\t")] = Number(cols[1]) || 0
      else if (cols[0] === "D" && cols.length >= 2) done.push(cols.slice(1).join("\t"))
      else if (cols[0] === "J" && cols.length >= 2) tracker.learn(cols.slice(1).join("\t"))
    })
    for (var part in current) {
      var before = previous[part]
      var bytes = current[part]
      var speed = 0
      if (before && now > before.time) {
        var instant = Math.max(0, (bytes - before.bytes) * 1000 / (now - before.time))
        speed = before.speed ? before.speed * 0.6 + instant * 0.4 : instant
      }
      var since = before ? before.since : now
      current[part] = { bytes: bytes, time: now, speed: speed, since: since }
      var total = known[part] ? known[part].total : 0
      if (!total && now - since < 3000) waiting = true
      rows.push({ name: finalName(part), part: part, bytes: bytes, speed: speed, total: total })
    }
    var vanished = []
    for (var old in previous) {
      if (old in current) continue
      vanished.push(finalName(old))
      lastBytes[finalName(old)] = known[old] && known[old].total ? known[old].total : previous[old].bytes
    }
    for (var k in known) if (!(k in current) && !(k in previous)) delete known[k]
    previous = current
    items = rows
    awaitingSize = waiting
    pendingFinals = vanished
    if (done.length) {
      finishedName = done[done.length - 1]
      finishedBytes = lastBytes[finishedName] || 0
      lastBytes = ({})
      finishedTimer.restart()
    }
    if (vanished.length) Qt.callLater(poll)
  }

  Timer {
    id: finishedTimer
    interval: 4500
    onTriggered: tracker.finishedName = ""
  }
  function dismissFinished() {
    finishedTimer.stop()
    finishedName = ""
  }
}
