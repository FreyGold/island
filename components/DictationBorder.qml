import QtQuick

// Only the outline moves. The text and controls keep their fixed positions.
Canvas {
  id: border
  required property var theme
  property bool active: false
  property bool notch: false
  property real cornerRadius: 28
  readonly property real padding: 8
  property real phase: 0
  property real strength: active ? 1 : 0

  visible: active || strength > 0.001
  antialiasing: true
  Behavior on strength {
    NumberAnimation { duration: 220 * border.theme.motionScale; easing.type: Easing.OutCubic }
  }
  onStrengthChanged: requestPaint()
  onWidthChanged: requestPaint()
  onHeightChanged: requestPaint()
  onCornerRadiusChanged: requestPaint()
  onNotchChanged: requestPaint()
  onVisibleChanged: if (visible) requestPaint()

  Timer {
    interval: 33
    repeat: true
    running: border.visible
    onTriggered: {
      border.phase += 0.033 / border.theme.motionScale
      border.requestPaint()
    }
  }

  function pointAt(distance, w, h, top, bottom) {
    var d = distance
    if (d < w - 2 * top) return { x: top + d, y: 0, nx: 0, ny: -1 }
    d -= w - 2 * top
    if (d < Math.PI * top / 2) return arc(w - top, top, top, -Math.PI / 2 + d / top)
    d -= Math.PI * top / 2
    if (d < h - top - bottom) return { x: w, y: top + d, nx: 1, ny: 0 }
    d -= h - top - bottom
    if (d < Math.PI * bottom / 2) return arc(w - bottom, h - bottom, bottom, d / bottom)
    d -= Math.PI * bottom / 2
    if (d < w - 2 * bottom) return { x: w - bottom - d, y: h, nx: 0, ny: 1 }
    d -= w - 2 * bottom
    if (d < Math.PI * bottom / 2) return arc(bottom, h - bottom, bottom, Math.PI / 2 + d / bottom)
    d -= Math.PI * bottom / 2
    if (d < h - top - bottom) return { x: 0, y: h - bottom - d, nx: -1, ny: 0 }
    d -= h - top - bottom
    return top > 0 ? arc(top, top, top, Math.PI + d / top) : { x: 0, y: 0, nx: -1, ny: 0 }
  }

  function arc(cx, cy, radius, angle) {
    var nx = Math.cos(angle), ny = Math.sin(angle)
    return { x: cx + radius * nx, y: cy + radius * ny, nx: nx, ny: ny }
  }

  onPaint: {
    var ctx = getContext("2d")
    ctx.reset()
    var w = width - 2 * padding, h = height - 2 * padding
    if (w <= 0 || h <= 0) return
    var bottom = Math.min(cornerRadius, h / 2, w / 2)
    var top = notch ? 0 : bottom
    var perimeter = 2 * (w + h) + (Math.PI - 4) * (top + bottom)
    var points = []
    for (var i = 0; i < 160; i++) {
      var t = i / 160
      var p = pointAt(t * perimeter, w, h, top, bottom)
      var ripple = 0.50 * Math.sin(t * Math.PI * 10 - phase * 1.7)
        + 0.30 * Math.sin(t * Math.PI * 18 + phase * 1.1)
        + 0.20 * Math.sin(t * Math.PI * 6 - phase * 0.8)
      var taper = notch ? Math.min(1, Math.max(0, p.y / 18)) : 1
      var offset = 3.2 * strength * ripple * taper
      points.push({ x: padding + p.x + p.nx * offset, y: padding + p.y + p.ny * offset })
    }
    var last = points[points.length - 1], first = points[0]
    ctx.beginPath()
    ctx.moveTo((last.x + first.x) / 2, (last.y + first.y) / 2)
    for (var j = 0; j < points.length; j++) {
      var current = points[j], next = points[(j + 1) % points.length]
      ctx.quadraticCurveTo(current.x, current.y, (current.x + next.x) / 2, (current.y + next.y) / 2)
    }
    ctx.closePath()
    ctx.fillStyle = theme.background
    ctx.fill()
    ctx.lineWidth = 0.7 * strength
    ctx.strokeStyle = Qt.rgba(1, 1, 1, 0.12 * strength)
    if (strength > 0.001) ctx.stroke()
  }
}
