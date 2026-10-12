import QtQuick
import QtQuick.Layouts
import Quickshell.Services.Pipewire
import "../../components"

// The Microphone card: the input volume, and the input picker behind its ›
// button. Loaded by the ControlCenter (and its gallery, as a preview).
CcSection {
  id: card
  readonly property var controls: center.controls
  readonly property bool galleryPreview: parent.galleryPreview
  anchors.fill: parent
  title: "Microphone"
  detail: !card.controls.controlPresent("microphone") ? "Unavailable" : card.controls.microphoneMuted ? "Muted" : Math.round(card.controls.microphoneVolume * 100) + "%"
  showChevron: !galleryPreview && !card.center.editMode && card.controls.inputs.length > 1
  chevronOpen: card.center.inputsOpen
  chevronLabel: "Microphone Input"
  chevronHideLabel: "Hide Inputs"
  onChevronClicked: { card.center.inputsOpen = !card.center.inputsOpen; card.center.outputsOpen = false }

  CcSlider {
    center: card.center
    enabled: card.controls.microphoneReady
    icon: "󰍬"
    value: card.controls.microphoneVolume
    onMoved: function(v) {
      if (card.controls.microphoneReady) card.controls.microphoneSource.audio.volume = v
    }
    Tooltip { theme: center.host.theme; text: "Microphone Input Volume" }
  }
  Repeater {
    model: !galleryPreview && card.center.inputsOpen && !card.center.editMode ? card.controls.inputs : []
    delegate: CcDeviceRow {
      required property var modelData
      center: card.center
      device: modelData
      selected: modelData === card.controls.microphoneSource
      icon: "󰍬"
      onPicked: Pipewire.preferredDefaultAudioSource = modelData
    }
  }
}
