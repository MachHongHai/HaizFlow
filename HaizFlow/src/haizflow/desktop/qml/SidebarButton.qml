import QtQuick
import QtQuick.Controls.Basic
import "."

Button {
    id: root

    property bool selected: false
    property bool compact: false
    property string iconGlyph: ""

    implicitHeight: 46
    leftPadding: compact ? 0 : 14
    rightPadding: compact ? 0 : 12
    font.pixelSize: Theme.body
    font.weight: selected ? Font.DemiBold : Font.Medium
    focusPolicy: Qt.TabFocus
    Accessible.name: text

    contentItem: Item {
        Row {
            id: navContent
            x: root.compact ? Math.round((parent.width - width) / 2) : root.leftPadding
            anchors.verticalCenter: parent.verticalCenter
            spacing: 0

            AppIcon {
                visible: root.compact
                width: visible ? Theme.iconLarge : 0
                height: visible ? 24 : 0
                glyph: root.iconGlyph
                iconSize: Theme.icon
                iconColor: root.selected ? Theme.interactive : Theme.textOnDarkMuted
            }

            Text {
                visible: !root.compact
                height: 24
                text: root.text
                color: root.selected ? Theme.textOnDark : Theme.textOnDarkMuted
                font: root.font
                verticalAlignment: Text.AlignVCenter
                textFormat: Text.PlainText
                elide: Text.ElideNone
            }
        }
    }

    background: Rectangle {
        id: navBackground
        radius: Theme.radiusSmall
        color: root.selected ? Theme.sidebarSelected : root.hovered ? Theme.sidebarHover : "transparent"
        border.width: root.activeFocus ? 2 : 0
        border.color: Theme.focus

        Rectangle {
            width: 3
            height: root.selected ? 24 : 0
            radius: 2
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            color: Theme.interactive
        }
    }

    ToolTip.visible: compact && hovered
    ToolTip.text: text
    ToolTip.delay: 450
}
