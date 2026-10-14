import QtQuick
import "."

Text {
    property real seconds: 0

    function formatTime(value) {
        const milliseconds = Math.max(0, Math.round(Number(value || 0) * 1000))
        const minutes = Math.floor(milliseconds / 60000)
        const wholeSeconds = Math.floor((milliseconds % 60000) / 1000)
        const remainder = milliseconds % 1000
        return String(minutes).padStart(2, "0") + ":"
            + String(wholeSeconds).padStart(2, "0") + "."
            + String(remainder).padStart(3, "0")
    }

    text: formatTime(seconds)
    color: Theme.textMuted
    font.family: "Cascadia Mono"
    font.pixelSize: TypeScale.metadata
    textFormat: Text.PlainText
}
