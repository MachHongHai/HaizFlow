import QtQuick
import "."

Item {
    id: root

    property string label: I18n.t("No preview")
    readonly property bool compact: Math.min(width, height) < 72
    clip: true

    Column {
        anchors.centerIn: parent
        width: Math.max(0, parent.width - Theme.space16)
        spacing: root.compact ? Theme.space4 : Theme.space8

        AppIcon {
            anchors.horizontalCenter: parent.horizontalCenter
            width: 28
            height: 28
            visible: !root.compact
            glyph: "\uE714"
            iconColor: Theme.textSubtle
            iconSize: Theme.iconLarge
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            width: parent.width
            text: root.label
            color: Theme.textSubtle
            font.pixelSize: root.compact ? Theme.label : Theme.caption
            textFormat: Text.PlainText
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            maximumLineCount: root.compact ? 1 : 2
            elide: Text.ElideRight
        }
    }
}
