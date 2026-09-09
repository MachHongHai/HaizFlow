import QtQuick

Item {
    id: root

    property string platform: ""
    readonly property string key: platform.toLowerCase()
    readonly property var mark: ({
        "youtube": { "glyph": "▶", "color": "#E53935" },
        "tiktok": { "glyph": "♪", "color": "#25C9CC" },
        "douyin": { "glyph": "♪", "color": "#F0527B" },
        "bilibili": { "glyph": "B", "color": "#F178A6" },
        "instagram": { "glyph": "◎", "color": "#C94B83" },
        "facebook": { "glyph": "f", "color": "#4D8DFF" },
        "x": { "glyph": "X", "color": "#A5B4C8" },
        "vimeo": { "glyph": "v", "color": "#32A9DD" },
        "dailymotion": { "glyph": "d", "color": "#6F93FF" },
        "twitch": { "glyph": "T", "color": "#9B7BFF" },
        "reddit": { "glyph": "r", "color": "#F36D45" },
        "vk": { "glyph": "vk", "color": "#5D8CC8" }
    })[key] || { "glyph": "•", "color": "#64748B" }

    implicitWidth: 22
    implicitHeight: 22

    Rectangle {
        anchors.fill: parent
        radius: 5
        color: root.mark.color

        Text {
            anchors.centerIn: parent
            text: root.mark.glyph
            color: "#FFFFFF"
            font.pixelSize: root.mark.glyph.length > 1 ? 8 : 14
            font.weight: Font.DemiBold
            verticalAlignment: Text.AlignVCenter
            textFormat: Text.PlainText
        }
    }

    Accessible.ignored: true
}
