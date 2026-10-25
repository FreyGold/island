import QtQuick
import Quickshell.Widgets

// Dynamic Island–style notification pill: the notification's image or app
// icon in a rounded tile, with the title and one line of body beside it.
// Styled like an iOS banner: the title with the time beside it, and the body
// below.
Item {
  id: pill
  required property var host
  // The island rectangle; the app tile sizes itself from its height.
  required property Item shape
  readonly property var row: host.notifications.last || ({})
  property bool imageFailed: false
  onRowChanged: imageFailed = false
  readonly property string iconSource: host.notifications.iconSource(host.notifications.last, imageFailed)
  readonly property var brand: host.notifications.brand(row)
  readonly property bool codexApproval: host.notifications.agent(row) === "codex"
    && /^Codex needs (confirmation|your reply)$/.test(host.notifications.title(row))
  readonly property var bodyLines: String(row.body || "").split("\n")
  readonly property string contextLine: bodyLines.length > 1 ? bodyLines[0] : ""
  readonly property string detailLine: bodyLines.length > 1 ? bodyLines.slice(1).join(" ") : String(row.body || row.app || "")

    opacity: host.notificationPill ? 1 : 0
  visible: opacity > 0.01
  Behavior on opacity { MotionAnimation { theme: host.theme; pace: "fade"; curve: "fade" } }

  ClippingRectangle {
    id: appTile
    anchors.left: parent.left
    anchors.leftMargin: 15
    anchors.verticalCenter: parent.verticalCenter
    // Grows with the pill so it never pokes past the rounded ends.
    width: height
    height: Math.max(0, Math.min(54, shape.height - 30))
    radius: height * 0.28
    color: "transparent"
    Rectangle {
      anchors.fill: parent
      visible: appTileImage.status !== Image.Ready
      gradient: Gradient {
        GradientStop { position: 0; color: pill.brand ? Qt.lighter(pill.brand.tile, 1.12) : Qt.lighter(host.theme.accent, 1.25) }
        GradientStop { position: 1; color: pill.brand ? pill.brand.tile : host.theme.accent }
      }
    }
    Image {
      id: appTileImage
      anchors.fill: parent
      source: pill.iconSource
      sourceSize.width: 100
      sourceSize.height: 100
      fillMode: Image.PreserveAspectCrop
      asynchronous: true
      visible: status === Image.Ready
      onStatusChanged: if (status === Image.Error) pill.imageFailed = true
    }
    Text {
      anchors.centerIn: parent
      visible: appTileImage.status !== Image.Ready
      text: pill.brand ? pill.brand.glyph : String(pill.row.glyph || "") || "󰂚"
      color: pill.brand ? pill.brand.ink : host.theme.accentText
      font.family: pill.brand ? "JetBrainsMono Nerd Font" : host.theme.fontFamily
      font.pixelSize: pill.brand ? Math.round(parent.height * 0.6) : pill.host.theme.px(24)
    }
  }

  Column {
    id: content
    anchors.left: appTile.right
    anchors.leftMargin: 12
    anchors.right: parent.right
    anchors.rightMargin: 30
    anchors.verticalCenter: parent.verticalCenter
    spacing: codexApproval ? 1 : 2
    Item {
      width: parent.width
      height: title.height
      Text {
        id: title
        anchors.left: parent.left
        anchors.right: age.left
        anchors.rightMargin: 8
        text: host.notifications.title(pill.row)
        textFormat: Text.PlainText
        elide: Text.ElideRight
        // iOS's type: a semibold title and a regular body of nearly the same
        // size, in SF's stand-in (Adwaita Sans).
        color: "#ffffff"
        font.family: host.theme.textFontFamily
        font.pixelSize: host.theme.px(15)
        font.weight: Font.DemiBold
        font.letterSpacing: -0.2
      }
      Text {
        id: age
        anchors.right: parent.right
        anchors.baseline: title.baseline
        text: host.notifications.age(pill.row.timestamp)
        textFormat: Text.PlainText
        color: Qt.rgba(1, 1, 1, 0.45)
        font.family: host.theme.textFontFamily
        font.pixelSize: host.theme.px(13)
      }
    }
    Text {
      width: parent.width
      text: String(pill.row.body || pill.row.app || "")
      visible: !codexApproval && text !== ""
      textFormat: Text.PlainText
      elide: Text.ElideRight
      color: Qt.rgba(1, 1, 1, 0.72)
      font.family: host.theme.textFontFamily
      font.pixelSize: host.theme.px(13)
      font.letterSpacing: -0.1
    }

    // A permission request has two useful facts after its title: where the
    // session is, and what Codex wants to do. Keep them visually separate so
    // the command reads as a request, not a third paragraph of plain text.
    Item {
      visible: codexApproval && contextLine !== ""
      width: parent.width
      height: 16
      Rectangle {
        id: contextDot
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        width: 5
        height: 5
        radius: width / 2
        color: "#8b8cf7"
      }
      Text {
        anchors.left: contextDot.right
        anchors.leftMargin: 7
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        text: contextLine
        textFormat: Text.PlainText
        elide: Text.ElideRight
        color: Qt.rgba(1, 1, 1, 0.68)
        font.family: host.theme.textFontFamily
        font.pixelSize: host.theme.px(12)
        font.weight: Font.Medium
        font.letterSpacing: -0.1
      }
    }
    Item {
      id: approvalDetail
      visible: codexApproval && detailLine !== ""
      width: parent.width
      height: 17
      clip: true
      Rectangle {
        anchors.left: parent.left
        anchors.top: approvalText.top
        width: 2
        height: approvalText.height
        radius: 1
        color: "#8b8cf7"
      }
      Text {
        id: approvalText
        anchors.left: parent.left
        anchors.leftMargin: 8
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        text: detailLine
        textFormat: Text.PlainText
        elide: Text.ElideRight
        color: Qt.rgba(1, 1, 1, 0.84)
        font.family: host.theme.textFontFamily
        font.pixelSize: host.theme.px(12)
        font.weight: Font.Normal
        font.letterSpacing: -0.1
      }
      // QML's elide is still used for layout. This mask makes the last words
      // dissolve into the island instead of ending on a hard glyph edge.
      Rectangle {
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        width: 34
        height: parent.height
        color: "transparent"
        gradient: Gradient {
          orientation: Gradient.Horizontal
          GradientStop { position: 0; color: "transparent" }
          GradientStop { position: 1; color: host.theme.background }
        }
      }
    }
  }
}
