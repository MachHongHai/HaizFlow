import QtMultimedia

AudioOutput {
    readonly property MediaDevices outputDevices: MediaDevices {}
    device: outputDevices.defaultAudioOutput
}
