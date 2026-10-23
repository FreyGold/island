.pragma library

// The meeting apps the Meetings addon knows. A mic stream is an app's when
// PipeWire's application.process.binary (or application.name) is one of its
// `binaries`; its call lives in a window whose class matches `windowClass`.
// `keys` are the app's own shortcuts ([Hyprland mods, key]) for muting
// (every app has one), the camera, sharing (sent with the window brought
// forward, since it opens the app's share menu), and hanging up; an action
// without one brings the window forward instead. A browser is only on a
// call in a tab one of its `sites` names by title, each with its own keys
// and `icons`, the icon names tried before the browser's own.
// Each app but the browser has an addon switch named by its id (see
// Addons.qml), and a site shares the switch of the app it's the web version
// of, or has its own (Meet).
var teamsKeys = { mic: ["CTRL SHIFT", "M"], camera: ["CTRL SHIFT", "O"], share: ["CTRL SHIFT", "E"], hangup: ["CTRL SHIFT", "H"] }
var zoomKeys = { mic: ["ALT", "A"], camera: ["ALT", "V"], share: ["ALT", "S"], hangup: ["ALT", "Q"] }
var discordKeys = { mic: ["CTRL SHIFT", "M"] }
var slackKeys = { mic: ["CTRL SHIFT", "SPACE"] }

var apps = [
  { id: "teams", name: "Teams", binaries: ["teams-for-linux"], windowClass: "^teams-for-linux$", keys: teamsKeys },
  { id: "zoom", name: "Zoom", binaries: ["zoom", "zoom.real"], windowClass: "^zoom", keys: zoomKeys },
  { id: "discord", name: "Discord", binaries: ["discord", "vesktop", "webcord"],
    windowClass: "^(discord|vesktop|webcord)$", keys: discordKeys },
  { id: "slack", name: "Slack", binaries: ["slack"], windowClass: "^slack$", keys: slackKeys },
  { id: "browser", name: "Browser",
    binaries: ["firefox", "zen", "zen-bin", "librewolf", "chromium", "chrome", "google-chrome", "brave", "vivaldi-bin", "msedge"],
    windowClass: "^(firefox|zen.*|librewolf|chromium|google-chrome|brave-browser|vivaldi.*|microsoft-edge|chrome-.*|brave-.*)$",
    sites: [
      { id: "meet", name: "Meet", title: "^Meet |Google Meet", keys: { mic: ["CTRL", "D"], camera: ["CTRL", "E"] } },
      { id: "teams", name: "Teams", title: "Microsoft Teams", keys: teamsKeys },
      { id: "zoom", name: "Zoom", title: "Zoom", keys: zoomKeys },
      { id: "discord", name: "Discord", title: "Discord", keys: discordKeys },
      { id: "slack", name: "Slack", title: "Slack", keys: slackKeys }
    ] }
]

// The app a stream's properties belong to, or null. An app on the
// system's Electron (Vesktop) reports only "electron": then `windowClass`,
// the class of the window its process (or that one's parent) owns, names it.
function appFor(props, windowClass) {
  var names = [props["application.process.binary"], props["application.name"]]
    .filter(function(n) { return !!n }).map(function(n) { return String(n).toLowerCase() })
  for (var i = 0; i < apps.length; i++)
    for (var j = 0; j < names.length; j++)
      if (apps[i].binaries.indexOf(names[j]) >= 0) return apps[i]
  if (windowClass)
    for (var k = 0; k < apps.length; k++)
      if (new RegExp(apps[k].windowClass, "i").test(windowClass)) return apps[k]
  return null
}
