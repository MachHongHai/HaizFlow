pragma ComponentBehavior: Bound
import QtQuick

Item {
    id: root

    property string text: ""
    property real progress: 0
    property real preferredPixelSize: 36
    property real maximumTextWidth: 640
    property color pendingColor: "#FFFFFF"
    property color spokenColor: "#FFEF00"

    width: Math.min(maximumTextWidth, Math.max(1, baseText.implicitWidth))
    height: Math.max(1, baseText.implicitHeight)

    FontLoader {
        id: karaokeFont
        source: "../../assets/fonts/Bangers-Regular.ttf"
    }

    Text {
        id: baseText
        anchors.centerIn: parent
        width: root.width
        text: root.text
        color: root.pendingColor
        font.family: karaokeFont.name
        font.pixelSize: root.preferredPixelSize
        font.weight: Font.Bold
        // Render uses one fixed font size for every cue. Long captions are
        // split over time, never squeezed horizontally or silently reduced.
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        wrapMode: Text.NoWrap
        style: Text.Outline
        styleColor: "#F0000000"
        textFormat: Text.PlainText
    }

    Item {
        x: 0
        y: 0
        width: root.width * Math.max(0, Math.min(1, root.progress))
        height: root.height
        clip: true

        Text {
            x: 0
            y: 0
            width: root.width
            height: root.height
            text: root.text
            color: root.spokenColor
            font.family: karaokeFont.name
            font.pixelSize: root.preferredPixelSize
            font.weight: Font.Bold
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.NoWrap
            style: Text.Outline
            styleColor: "#F0000000"
            textFormat: Text.PlainText
        }
    }
}
