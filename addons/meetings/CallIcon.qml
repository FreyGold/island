import QtQuick
import QtQuick.Shapes
import "../../components"

// The call's icons drawn as SF Symbols' filled ones, on a 24-unit grid
// scaled to `size`: "mic", "video", "display", "phone" and "phone.down".
// `slashed` strikes it through, drawn on and off, cut out of the glyph in
// `knockout`, the colour behind it.
Item {
  id: icon
  property string name: "mic"
  property color color: "white"
  property color knockout: "black"
  property bool slashed: false
  property var theme: null
  property real size: 20
  // How far the slash is drawn, 0 to 1.
  property real slash: slashed ? 1 : 0
  Behavior on slash { MotionAnimation { theme: icon.theme; pace: "expressive" } }
  width: size
  height: size

  Shape {
    width: 24
    height: 24
    anchors.centerIn: parent
    scale: icon.size / 24
    preferredRendererType: Shape.CurveRenderer

    // Filled parts.
    ShapePath {
      strokeColor: "transparent"
      fillColor: icon.color
      PathSvg {
        path: icon.name === "mic" ? "M12 2.5 a3.2 3.2 0 0 1 3.2 3.2 v5.6 a3.2 3.2 0 0 1 -6.4 0 v-5.6 A3.2 3.2 0 0 1 12 2.5 Z"
          : icon.name === "video" ? "M5.2 6.5 h8.6 a2.4 2.4 0 0 1 2.4 2.4 v6.2 a2.4 2.4 0 0 1 -2.4 2.4 h-8.6 a2.4 2.4 0 0 1 -2.4 -2.4 v-6.2 a2.4 2.4 0 0 1 2.4 -2.4 Z M17.4 10.4 l3 -2.1 a0.8 0.8 0 0 1 1.3 0.7 v6 a0.8 0.8 0 0 1 -1.3 0.7 l-3 -2.1 Z"
          : icon.name === "display" ? "M4.6 4 h14.8 a2.1 2.1 0 0 1 2.1 2.1 v8.6 a2.1 2.1 0 0 1 -2.1 2.1 h-14.8 a2.1 2.1 0 0 1 -2.1 -2.1 v-8.6 a2.1 2.1 0 0 1 2.1 -2.1 Z M10.6 16.8 h2.8 v2.4 h-2.8 Z M8 19 h8 a0.9 0.9 0 0 1 0 1.8 h-8 a0.9 0.9 0 0 1 0 -1.8 Z"
          : icon.name === "phone" ? "M6.9 2.9 c0.7 -0.3 1.5 0 1.8 0.7 l1.5 3.3 c0.3 0.6 0.1 1.3 -0.4 1.7 l-1.4 1.1 c0.9 2 2.4 3.6 4.4 4.5 l1.1 -1.4 c0.4 -0.5 1.1 -0.7 1.7 -0.4 l3.3 1.5 c0.7 0.3 1 1.1 0.7 1.8 l-0.8 1.9 c-0.5 1.1 -1.7 1.8 -2.9 1.5 C9.6 18.1 5.9 14.4 4.4 8.1 c-0.3 -1.2 0.4 -2.4 1.5 -2.9 Z"
          : "M2.3 13.4 c0 -2.8 4.4 -4.9 9.7 -4.9 s9.7 2.1 9.7 4.9 v1.3 c0 0.9 -0.8 1.5 -1.6 1.4 l-3.1 -0.5 c-0.7 -0.1 -1.2 -0.7 -1.2 -1.4 v-1.5 c-1.2 -0.4 -2.5 -0.6 -3.8 -0.6 s-2.6 0.2 -3.8 0.6 v1.5 c0 0.7 -0.5 1.3 -1.2 1.4 l-3.1 0.5 c-0.8 0.1 -1.6 -0.5 -1.6 -1.4 Z"
      }
    }
    // The mic's stand.
    ShapePath {
      strokeColor: icon.name === "mic" ? icon.color : "transparent"
      strokeWidth: 1.8
      fillColor: "transparent"
      capStyle: ShapePath.RoundCap
      PathSvg { path: "M6.6 10.8 a5.4 5.4 0 0 0 10.8 0 M12 16.4 v3.6 M9 20.4 h6" }
    }
    // The slash, with a gap cut either side of it, drawn on from the top.
    ShapePath {
      strokeColor: icon.slash > 0.01 ? icon.knockout : "transparent"
      strokeWidth: 4.6
      fillColor: "transparent"
      capStyle: ShapePath.RoundCap
      startX: 4.2; startY: 3.6
      PathLine { x: 4.2 + 15.6 * icon.slash; y: 3.6 + 16.8 * icon.slash }
    }
    ShapePath {
      strokeColor: icon.slash > 0.01 ? icon.color : "transparent"
      strokeWidth: 1.8
      fillColor: "transparent"
      capStyle: ShapePath.RoundCap
      startX: 4.2; startY: 3.6
      PathLine { x: 4.2 + 15.6 * icon.slash; y: 3.6 + 16.8 * icon.slash }
    }
  }
}
