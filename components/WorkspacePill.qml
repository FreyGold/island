import QtQuick

// Shows the active workspace as a page-control dot.
Item {
  id: pill
  required property var host
  readonly property bool shown: host.workspacesPill
  readonly property int indicatorSize: 6
  readonly property int slot: 12
  readonly property int gap: 4

  opacity: shown ? 1 : 0
  visible: opacity > 0.01
  Behavior on opacity { MotionAnimation { theme: pill.host.theme; pace: "fade"; curve: "fade" } }

  Item {
    anchors.centerIn: parent
    width: pill.host.workspaceIds.length * (pill.slot + pill.gap) - pill.gap
    height: pill.slot

    Row {
      spacing: pill.gap
      Repeater {
        model: pill.host.workspaceIds
        delegate: Item {
          id: workspaceSlot
          required property int modelData
          readonly property bool focused: modelData === pill.host.focusedWorkspaceId
          width: pill.slot
          height: pill.slot
          Rectangle {
            anchors.centerIn: parent
            width: pill.indicatorSize
            height: pill.indicatorSize
            radius: width / 2
            color: workspaceSlot.focused ? "#e2e6de" : Qt.rgba(1, 1, 1, 0.32)
          }
        }
      }
    }
  }
}
