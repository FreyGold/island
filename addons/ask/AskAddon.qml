import QtQuick
import ".."

// Ask AI: text typed in the launcher can be sent to Claude, Codex, or Gemini (the
// Ask row, see launcherRow), answered Siri-style in the island (see
// AnswerView) through the command-line tool you're signed in to.
Addon {
  id: askAddon
  views: [{ name: "answer", component: answerView }]
  launcherHint: "ask"

  Component {
    id: answerView
    AnswerView { host: askAddon.host; ask: askAddon; active: askAddon.host.view === "answer" }
  }

  readonly property var providers: ({
    claude: { name: "Claude", cli: "claude", glyph: "", tile: "#d97757", ink: "#ffffff" },
    codex: { name: "Codex", cli: "codex", glyph: "", tile: "#f2f2f2", ink: "#000000" },
    gemini: { name: "Gemini", cli: "agy", glyph: "✦", tile: "#1a73e8", ink: "#ffffff" },
    agy: { name: "Gemini", cli: "agy", glyph: "✦", tile: "#1a73e8", ink: "#ffffff" }
  })
  readonly property var provider: providers[addon.option("with")] || providers.codex
  readonly property string geminiModel: addon.option("geminiModel") || addon.option("model") || "gemini-3.8-flash-low"
  readonly property string claudeModel: addon.option("claudeModel") || "haiku"
  readonly property string codexModel: addon.option("codexModel") || "gpt-5.6-terra"
  readonly property string model: {
    if (provider.cli === "claude") return claudeModel
    if (provider.cli === "codex") return codexModel
    return geminiModel
  }
  readonly property bool menuSearch: addon.option("menuSearch") !== false

  property string question: ""
  function ask(text) {
    text = String(text || "").trim()
    if (!text) return
    question = text
    host.view = "answer"
  }

  // The Ask row: first when the text reads like a question.
  function launcherRow(text) {
    return {
      glyph: provider.glyph, tile: provider.tile, ink: provider.ink,
      label: "Ask " + provider.name, detail: "“" + text + "”",
      first: looksLikeQuestion(text),
      run: function() { askAddon.ask(text) }
    }
  }
  function looksLikeQuestion(text) {
    if (/\?$/.test(text)) return true
    var words = text.split(/\s+/)
    return words.length >= 3
      && /^(who|what|when|where|why|how|which|whose|can|could|should|would|is|are|was|were|do|does|did|will|explain|write|tell|give|summari[sz]e|translate|define|compare|help)$/i.test(words[0])
  }
}
