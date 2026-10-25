import QtQuick
import QtQuick.Layouts
import Quickshell.Hyprland
import "../../components"

// A compact operational list. Status is the only coloured element, so task
// names remain the focus and the list stays readable at a glance.
Item {
  id: view
  required property var codex
  property bool active: false
  readonly property var host: codex.host
  readonly property var theme: host.theme
  readonly property var sessions: codex.sessions || []
  readonly property int workingCount: sessions.filter(function(row) { return row.status === "working" }).length
  readonly property int actionCount: sessions.filter(function(row) {
    return row.status === "needsAction" || row.status === "failed" || row.status === "interrupted"
  }).length

  implicitWidth: 480
  implicitHeight: content.implicitHeight
  // Addon surfaces measure their child before they give it a final width.
  // Keep the designed content width during that first layout pass.
  width: implicitWidth

  onActiveChanged: if (active) Qt.callLater(function() { view.forceActiveFocus() })
  Keys.onEscapePressed: host.view = "rest"

  function statusText(row) {
    if (row.status === "needsAction") return String(row.detail || "Action required")
    if (row.status === "failed") return "Failed"
    if (row.status === "interrupted") return "Stopped"
    if (row.status === "finished") return "Finished"
    return "Working"
  }
  function statusColor(status) {
    if (status === "needsAction") return "#ff9f0a"
    if (status === "failed" || status === "interrupted") return "#ff453a"
    if (status === "finished") return "#30d158"
    return theme.accent
  }
  function pathText(path) {
    var value = String(path || "")
    var home = String(host.home || "")
    return home && value.indexOf(home) === 0 ? "~" + value.slice(home.length) : value
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
  function locationText(row) {
    var number = workspaceNumber(row)
    var workspace = number > 0 ? "Workspace " + number : "Workspace unavailable"
    var path = pathText(row.cwd)
    return path ? workspace + " · " + path : workspace
  }
  function subtitle() {
    if (actionCount > 0) return actionCount === 1 ? "1 session needs your action" : actionCount + " sessions need your action"
    if (workingCount > 0) return workingCount === 1 ? "1 session is working" : workingCount + " sessions are working"
    return sessions.length ? "Recent completed sessions" : "No active sessions"
  }

  ColumnLayout {
    id: content
    width: parent.width
    spacing: 16

    RowLayout {
      Layout.fillWidth: true
      spacing: 12
      Rectangle {
        Layout.preferredWidth: 36
        Layout.preferredHeight: 36
        radius: 10
        color: "#f2f2f2"
        Text {
          anchors.centerIn: parent
          text: ""
          color: "#000000"
          font.family: "JetBrainsMono Nerd Font"
          font.pixelSize: 20
        }
      }
      ColumnLayout {
        Layout.fillWidth: true
        spacing: 1
        Text {
          Layout.fillWidth: true
          text: "Codex Sessions"
          elide: Text.ElideRight
          color: theme.text
          font.family: theme.textFontFamily
          font.features: { "tnum": 1 }
          font.pixelSize: theme.px(19)
          font.weight: Font.DemiBold
          font.letterSpacing: -0.3
        }
        Text {
          Layout.fillWidth: true
          text: view.subtitle()
          elide: Text.ElideRight
          color: theme.secondary
          font.family: theme.textFontFamily
          font.pixelSize: theme.px(13)
        }
      }
    }

    Rectangle {
      Layout.fillWidth: true
      implicitHeight: sessions.length > 0 ? list.implicitHeight : 72
      radius: 12
      color: theme.solid("raised")
      border.width: 1
      border.color: theme.fill("subtle")

      Column {
        id: list
        width: parent.width
        visible: sessions.length > 0
        Repeater {
          model: sessions
          delegate: Item {
            id: row
            required property var modelData
            required property int index
            width: list.width
            height: 64
            Rectangle {
              width: 8
              height: 8
              radius: width / 2
              anchors.left: parent.left
              anchors.leftMargin: 16
              anchors.verticalCenter: parent.verticalCenter
              color: view.statusColor(row.modelData.status)
            }
            Column {
              anchors.left: parent.left
              anchors.leftMargin: 34
              anchors.right: status.left
              anchors.rightMargin: 10
              anchors.verticalCenter: parent.verticalCenter
              spacing: 3
              Text {
                width: parent.width
                text: String(row.modelData.title || "Codex session")
                textFormat: Text.PlainText
                elide: Text.ElideRight
                color: theme.text
                font.family: theme.textFontFamily
                font.pixelSize: theme.px(15)
                font.weight: Font.Medium
              }
              Text {
                width: parent.width
                text: view.locationText(row.modelData)
                textFormat: Text.PlainText
                elide: Text.ElideMiddle
                color: theme.secondary
                font.family: theme.textFontFamily
                font.pixelSize: theme.px(12)
              }
            }
            Text {
              id: status
              anchors.right: parent.right
              anchors.rightMargin: 16
              anchors.verticalCenter: parent.verticalCenter
              text: view.statusText(row.modelData)
              color: view.statusColor(row.modelData.status)
              font.family: theme.textFontFamily
              font.pixelSize: theme.px(12)
              font.weight: Font.Medium
            }
            Rectangle {
              visible: row.index < sessions.length - 1
              anchors.left: parent.left
              anchors.leftMargin: 34
              anchors.right: parent.right
              anchors.rightMargin: 16
              anchors.bottom: parent.bottom
              height: 1
              color: theme.fill("subtle")
            }
          }
        }
      }
      Text {
        anchors.centerIn: parent
        visible: sessions.length === 0
        text: codex.dataAvailable ? "No active Codex sessions" : "Codex session data is not available"
        color: theme.secondary
        font.family: theme.textFontFamily
        font.pixelSize: theme.px(14)
      }
    }

    Text {
      Layout.fillWidth: true
      visible: sessions.length > 0
      text: "Finished sessions stay here for five minutes."
      color: theme.secondary
      font.family: theme.textFontFamily
      font.pixelSize: theme.px(12)
    }
  }
}
