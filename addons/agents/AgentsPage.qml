pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import "../../components"

// The Agents pane: the agent and its plan, a card for each usage limit (the
// 5-hour session and the week) with when it resets, then tokens by day for
// the last six days and today. Limits colour as System Stats' load does.
ColumnLayout {
  id: page
  required property var view
  required property var agents
  property bool shown: false
  spacing: 20

  readonly property var record: agents.record
  readonly property var provider: agents.provider
  // Typed, so theme.withAlpha can tint it.
  readonly property color tint: provider.color
  readonly property var limits: record && record.limits || []
  readonly property var days: record && record.recentDays || []
  readonly property real busiest: Math.max.apply(null, [1].concat(days.map(function(d) { return d.messageCount || 0 })))
  readonly property real week: days.reduce(function(sum, d) { return sum + (d.messageCount || 0) }, 0)

  readonly property color red: "#ff453a"
  readonly property color green: "#30d158"
  readonly property color yellow: "#ffd60a"

  // A clock for the countdowns, ticking while the pane is open.
  property real now: Date.now()
  Timer {
    interval: 30000
    repeat: true
    running: page.shown
    triggeredOnStart: true
    onTriggered: page.now = Date.now()
  }

  // Used: green under half, yellow, red from 80%.
  function usedColor(p) { return p >= 0.8 ? red : p >= 0.5 ? yellow : green }
  function usedName(p) { return p >= 1 ? "Reached" : p >= 0.8 ? "High" : p >= 0.5 ? "Moderate" : "Normal" }
  // The collectors' labels ("Session (5-hour)", "5h window", "Weekly (7-day)").
  function limitTitle(label) {
    if (/5.?h/i.test(label)) return "5-Hour Limit"
    if (/week|7.?d/i.test(label)) return "Weekly Limit"
    return label
  }
  function countdown(iso) {
    var ms = new Date(iso).getTime() - now
    if (!isFinite(ms)) return "—"
    if (ms <= 0) return "Now"
    var minutes = Math.floor(ms / 60000), hours = Math.floor(minutes / 60), days = Math.floor(hours / 24)
    if (days > 0) return days + "d " + (hours % 24) + "h"
    if (hours > 0) return hours + "h " + (minutes % 60) + "m"
    return Math.max(1, minutes) + "m"
  }
  function resetTime(iso) {
    var at = new Date(iso)
    if (!isFinite(at.getTime())) return "—"
    var clock = Qt.formatTime(at, view.host.settings.clock24h ? "HH:mm" : "h:mm AP")
    return at.toDateString() === new Date(now).toDateString() ? clock : Qt.formatDate(at, "ddd") + " " + clock
  }
  function tokens(n) {
    n = n || 0
    if (n >= 1e9) return (n / 1e9).toFixed(1) + "B"
    if (n >= 1e6) return (n / 1e6).toFixed(1) + "M"
    if (n >= 1e3) return (n / 1e3).toFixed(1) + "K"
    return String(n)
  }
  // "YYYY-MM-DD" as a local day.
  function dayName(date, last) {
    if (last) return "Today"
    var p = String(date).split("-")
    return Qt.formatDate(new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2])), "ddd")
  }
  function updatedText() {
    if (agents.updating) return "Updating…"
    if (!record || !record.updatedAt) return ""
    var minutes = Math.floor((now - new Date(record.updatedAt).getTime()) / 60000)
    return minutes < 1 ? "Updated just now" : minutes < 60 ? "Updated " + minutes + " min ago" : "Updated " + resetTime(record.updatedAt)
  }

  ColumnLayout {
    Layout.fillWidth: true
    spacing: 10

    // The agent and its plan --------------------------------------------------
    Card {
      view: page.view
      Layout.fillWidth: true
      implicitHeight: 64
      RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 14
        anchors.rightMargin: 14
        spacing: 12
        Rectangle {
          Layout.preferredWidth: 36
          Layout.preferredHeight: 36
          radius: 9
          color: page.tint
          Text {
            anchors.centerIn: parent
            text: page.provider.glyph
            color: "#ffffff"
            font.family: page.view.host.theme.fontFamily
            font.pixelSize: page.view.host.theme.px(20)
          }
        }
        ColumnLayout {
          Layout.fillWidth: true
          spacing: 2
          RowLayout {
            spacing: 8
            Text {
              text: page.provider.name
              color: page.view.text
              font.family: "Adwaita Sans"
              font.pixelSize: page.view.detailFontSize + 1
              font.weight: Font.DemiBold
            }
            Rectangle {
              readonly property string plan: page.record && page.record.tierLabel || ""
              visible: plan !== ""
              Layout.preferredHeight: 20
              Layout.preferredWidth: planText.implicitWidth + 16
              radius: 10
              color: page.view.host.theme.withAlpha(page.tint, 0.16)
              Text {
                id: planText
                anchors.centerIn: parent
                text: parent.plan.charAt(0).toUpperCase() + parent.plan.slice(1)
                color: page.tint
                font.family: "Adwaita Sans"
                font.pixelSize: page.view.host.theme.px(12)
                font.weight: Font.DemiBold
              }
            }
          }
          Text {
            Layout.fillWidth: true
            text: page.updatedText()
            visible: text !== ""
            elide: Text.ElideRight
            color: page.view.textMuted
            font.family: "Adwaita Sans"
            font.pixelSize: page.view.host.theme.px(13)
          }
        }
        // Refresh now.
        Rectangle {
          Layout.preferredWidth: 30
          Layout.preferredHeight: 30
          radius: 15
          color: refreshArea.containsMouse ? page.view.host.theme.withAlpha(page.view.text, 0.1) : "transparent"
          Text {
            id: refreshGlyph
            anchors.centerIn: parent
            text: "󰑐"
            color: page.view.textMuted
            font.family: page.view.host.theme.fontFamily
            font.pixelSize: page.view.host.theme.px(16)
            RotationAnimation on rotation {
              running: page.agents.updating
              from: 0; to: 360; duration: 1000; loops: Animation.Infinite
              onRunningChanged: if (!running) refreshGlyph.rotation = 0
            }
          }
          MouseArea {
            id: refreshArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: page.agents.refresh()
          }
        }
      }
    }

    // The limits, side by side ------------------------------------------------
    RowLayout {
      visible: page.limits.length > 0
      Layout.fillWidth: true
      spacing: 10
      Repeater {
        // By count: each record's new array would otherwise replay the rings.
        model: page.limits.length
        delegate: StatCard {
          id: limit
          required property int index
          readonly property var modelData: page.limits[index] || ({ label: "", percent: 0, resetsAt: "" })
          readonly property real used: Math.max(0, Number(modelData.percent) || 0)
          view: page.view
          Layout.fillWidth: true
          Layout.preferredWidth: 1
          Layout.fillHeight: true
          icon: index === 0 ? "󱎫" : "󰃭"
          iconColor: page.tint
          ringColor: page.usedColor(used)
          title: page.limitTitle(modelData.label)
          value: used * 100
          rows: [
            { label: "Used", value: Math.round(used * 100) + "%" },
            { label: "Resets In", value: page.countdown(modelData.resetsAt) },
            { label: "Resets", value: page.resetTime(modelData.resetsAt) }
          ]
          status: page.usedName(used)
          statusColor: page.usedColor(used)
        }
      }
    }

    // No limits: why, and how to get them back.
    Card {
      visible: page.record !== null && page.limits.length === 0
      view: page.view
      Layout.fillWidth: true
      implicitHeight: noLimits.implicitHeight + 32
      ColumnLayout {
        id: noLimits
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 16
        spacing: 4
        Text {
          text: "Limits Unavailable"
          color: page.view.text
          font.family: "Adwaita Sans"
          font.pixelSize: page.view.detailFontSize
          font.weight: Font.DemiBold
        }
        Text {
          Layout.fillWidth: true
          wrapMode: Text.WordWrap
          text: (page.record && page.record.usageStatusText ? page.record.usageStatusText + ". " : "")
            + "Sign in with `" + page.provider.login + "` to see them; tokens are counted from this machine either way."
          textFormat: Text.MarkdownText
          color: page.view.textMuted
          font.family: "Adwaita Sans"
          font.pixelSize: page.view.host.theme.px(13)
        }
      }
    }

    // Tokens by day -----------------------------------------------------------
    Card {
      view: page.view
      Layout.fillWidth: true
      implicitHeight: tokenBody.implicitHeight + 32
      ColumnLayout {
        id: tokenBody
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 16
        spacing: 14
        RowLayout {
          Layout.fillWidth: true
          spacing: 8
          Text {
            text: "󰄨"
            color: page.tint
            font.family: page.view.host.theme.fontFamily
            font.pixelSize: page.view.host.theme.px(16)
          }
          Text {
            Layout.fillWidth: true
            text: "Tokens by Day"
            color: page.view.text
            font.family: "Adwaita Sans"
            font.pixelSize: page.view.detailFontSize + 1
            font.weight: Font.DemiBold
          }
          Text {
            text: page.tokens(page.week) + " this week"
            color: page.view.textMuted
            font.family: "Adwaita Sans"
            font.pixelSize: page.view.host.theme.px(13)
            font.features: { "tnum": 1 }
          }
        }
        Text {
          visible: page.record === null
          text: page.agents.updating ? "Reading usage…" : "No " + page.provider.name + " usage found on this machine."
          color: page.view.textMuted
          font.family: "Adwaita Sans"
          font.pixelSize: page.view.host.theme.px(13)
        }
        // One column a day: its total over a bar scaled to the busiest day,
        // its name under it; today in the agent's colour.
        RowLayout {
          visible: page.days.length > 0
          Layout.fillWidth: true
          spacing: 8
          Repeater {
            model: page.days.length
            delegate: ColumnLayout {
              id: day
              required property int index
              readonly property var modelData: page.days[index] || ({ date: "", messageCount: 0 })
              readonly property bool today: index === page.days.length - 1
              readonly property real count: modelData.messageCount || 0
              Layout.fillWidth: true
              Layout.preferredWidth: 1
              spacing: 6
              Text {
                Layout.alignment: Qt.AlignHCenter
                text: day.count > 0 ? page.tokens(day.count) : "—"
                color: day.today ? page.view.text : page.view.textMuted
                font.family: "Adwaita Sans"
                font.pixelSize: page.view.host.theme.px(12)
                font.weight: day.today ? Font.DemiBold : Font.Normal
                font.features: { "tnum": 1 }
              }
              Item {
                Layout.fillWidth: true
                Layout.preferredHeight: 120
                Rectangle {
                  anchors.horizontalCenter: parent.horizontalCenter
                  anchors.bottom: parent.bottom
                  width: Math.min(parent.width, 34)
                  height: parent.height
                  radius: 6
                  color: page.view.host.theme.withAlpha(page.view.text, 0.06)
                }
                Rectangle {
                  anchors.horizontalCenter: parent.horizontalCenter
                  anchors.bottom: parent.bottom
                  width: Math.min(parent.width, 34)
                  height: day.count > 0 ? Math.max(6, parent.height * day.count / page.busiest) : 0
                  Behavior on height { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }
                  radius: 6
                  color: day.today ? page.tint : page.view.host.theme.withAlpha(page.tint, 0.45)
                }
              }
              Text {
                Layout.alignment: Qt.AlignHCenter
                text: page.dayName(day.modelData.date, day.today)
                color: day.today ? page.view.text : page.view.textMuted
                font.family: "Adwaita Sans"
                font.pixelSize: page.view.host.theme.px(12)
                font.weight: day.today ? Font.DemiBold : Font.Normal
              }
            }
          }
        }
      }
    }
  }
}
