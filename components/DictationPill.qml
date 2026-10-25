import QtQuick
import QtQuick.Controls

Item {
  id: pill
  required property var host
  readonly property var dictation: host.dictation
  readonly property bool shown: host.dictationPill
  readonly property bool hasText: dictation.transcript.length > 0
  readonly property bool loading: shown && !dictation.error
    && (dictation.recording || dictation.phase === "transcribing")
  readonly property string title: dictation.error ? "Dictation needs attention"
    : dictation.phase === "done" ? "Copied to clipboard"
    : dictation.recording ? "Listening" : "Finishing dictation"

  opacity: shown ? 1 : 0
  visible: opacity > 0.01
  enabled: shown
  Behavior on opacity { MotionAnimation { theme: pill.host.theme; pace: "fade"; curve: "fade" } }

  Row {
    id: heading
    x: 20; y: 15
    spacing: 8
    Text {
      text: pill.dictation.phase === "done" ? "󰄬" : "󰍬"
      color: pill.dictation.error ? pill.host.theme.urgent : pill.host.theme.accent
      font.family: pill.host.theme.fontFamily
      font.pixelSize: pill.host.theme.px(16)
    }
    Text {
      text: pill.title
      color: pill.host.theme.text
      font.family: pill.host.theme.textFontFamily
      font.pixelSize: pill.host.theme.px(13)
      font.weight: Font.DemiBold
      font.letterSpacing: -0.2
    }
  }

  Text {
    anchors.right: stopButton.visible ? stopButton.left : parent.right
    anchors.rightMargin: stopButton.visible ? 12 : 20
    anchors.verticalCenter: heading.verticalCenter
    text: pill.dictation.timeText
    color: pill.host.theme.secondary
    font.family: pill.host.theme.textFontFamily
    font.pixelSize: pill.host.theme.px(12)
    font.features: { "tnum": 1 }
  }

  ToolButton {
    id: stopButton
    anchors.right: parent.right
    anchors.rightMargin: 14
    anchors.verticalCenter: heading.verticalCenter
    width: 28; height: 28
    visible: pill.dictation.recording
    Accessible.name: "Stop dictation"
    onClicked: pill.dictation.stop()
    background: Rectangle {
      radius: 14
      color: stopButton.hovered ? pill.host.theme.fill("strong") : pill.host.theme.fill("raised")
      border.width: stopButton.activeFocus ? 1 : 0
      border.color: pill.host.theme.accent
    }
    contentItem: Item {
      Rectangle {
        anchors.centerIn: parent
        width: 8; height: 8; radius: 2
        color: pill.host.theme.text
      }
    }
    ToolTip.visible: hovered
    ToolTip.text: "Stop dictation"
  }

  Flickable {
    id: preview
    x: 20; y: 43
    width: parent.width - 40
    height: parent.height - y - 16
    clip: true
    interactive: false
    contentWidth: width
    contentHeight: speech.height
    contentY: Math.max(0, contentHeight - height)
    Text {
      id: speech
      width: preview.width - (pill.loading ? 24 : 0)
      text: pill.dictation.error || pill.dictation.transcript || "Start speaking…"
      textFormat: Text.PlainText
      wrapMode: Text.Wrap
      color: pill.dictation.error ? pill.host.theme.urgent
        : pill.hasText ? pill.host.theme.text : pill.host.theme.secondary
      font.family: pill.host.theme.textFontFamily
      font.pixelSize: pill.host.theme.px(15)
      font.weight: Font.Normal
      font.letterSpacing: -0.15
      lineHeightMode: Text.FixedHeight
      lineHeight: pill.host.theme.px(20)
      onLineLaidOut: function(line) {
        if (!line.isLast) return
        loadingDots.x = line.x + line.implicitWidth + 6
        loadingDots.y = line.y + (line.height - loadingDots.height) / 2
      }
    }

    Row {
      id: loadingDots
      visible: pill.loading
      spacing: 3
      Accessible.name: "Transcribing"
      Repeater {
        model: 3
        delegate: Rectangle {
          id: dot
          required property int index
          width: 4; height: 4; radius: 2
          color: pill.host.theme.accent
          opacity: 0.25
          SequentialAnimation on opacity {
            running: pill.loading
            loops: Animation.Infinite
            PauseAnimation { duration: dot.index * 120 * pill.host.theme.motionScale }
            NumberAnimation { to: 1; duration: 200 * pill.host.theme.motionScale; easing.type: Easing.InOutSine }
            NumberAnimation { to: 0.25; duration: 240 * pill.host.theme.motionScale; easing.type: Easing.InOutSine }
            PauseAnimation { duration: ((2 - dot.index) * 120 + 160) * pill.host.theme.motionScale }
          }
        }
      }
    }
  }
}
