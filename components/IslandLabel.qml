import QtQuick

// The resting pill's clock, plus the plain-text feedback and setup warning
// that share its spot.
Text {
  id: label
  required property var host
  readonly property bool showingClock: host.view === "rest" && !host.setup.needsSetup
  // Hidden behind the notification, volume, clipboard, finished-download,
  // and addons' momentary and asking pills (the media, downloading,
  // recording, and addons' other ongoing pills keep the clock in the middle).
  opacity: !host.notificationPill && !host.volumePill && !host.clipboardPill && !host.activityPill && !host.workspacesPill && !host.dictationPill && !(host.addonPill && (host.view === "feedback" || host.addonPill.pillAsks)) && !host.downloadDone && (host.view === "rest" || host.view === "feedback") ? 1 : 0
  width: parent.width - 24
  horizontalAlignment: Text.AlignHCenter
  // Use the visible glyph bounds with a small downward optical correction.
  anchors.verticalCenterOffset: showingClock && clockInk.tightBoundingRect.height > 0
    ? Math.round(height / 2 - baselineOffset - clockInk.tightBoundingRect.y - clockInk.tightBoundingRect.height / 2) + 1 : 0
  elide: Text.ElideRight
  textFormat: Text.PlainText
  // Notifications have their own layout; don't flash their text in
  // this label while it fades out.
  text: host.view === "feedback" && !host.notificationPill && !host.volumePill ? host.feedback
    : host.setup.needsSetup ? "󰀦  " + host.setup.warning
    : host.clockText
  // A fixed soft off-white on the always-black island; the setup
  // warning keeps the theme's urgent color.
  color: host.view === "rest" && host.setup.needsSetup ? host.theme.urgent : "#e2e6de"
  // Adwaita Sans (Inter-based) at semibold; tabular figures keep the
  // digits from shifting as the time changes.
  font.family: host.theme.textFontFamily
  font.pixelSize: host.theme.px(showingClock ? 13 : 15)
  font.weight: Font.DemiBold
  // Apple-style: tabular digits, the colon raised to sit centered on them
  // (Inter's "case" forms), and SF's tight tracking.
  font.features: { "tnum": 1, "case": 1 }
  font.letterSpacing: -0.4
  TextMetrics { id: clockInk; font: label.font; text: label.text }
  // Get out of the way fast, fade back in gently.
  Behavior on opacity { MotionAnimation { theme: host.theme; pace: "fade"; curve: "fade" } }
}
