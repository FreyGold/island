import QtQuick

// A track's cover when it has none: a soft gradient in the cover tint (the
// theme accent, with no art to pick from) with a note on it, for the media
// pill and the player view.
Rectangle {
  id: fallback
  required property var host
  property real glyphSize: 14
  readonly property color tint: host.nowPlaying.tint
  gradient: Gradient {
    GradientStop { position: 0; color: Qt.lighter(fallback.tint, 1.12) }
    GradientStop { position: 1; color: Qt.darker(fallback.tint, 1.9) }
  }
  Text {
    anchors.centerIn: parent
    text: "󰝚"
    color: Qt.rgba(1, 1, 1, 0.92)
    font.family: fallback.host.theme.fontFamily
    font.pixelSize: fallback.host.theme.px(fallback.glyphSize)
  }
}
