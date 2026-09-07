import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Button {
    id: root

    property string iconName: ""

    implicitHeight: 62
    padding: Theme.space12
    focusPolicy: Qt.TabFocus

    contentItem: RowLayout {
        spacing: Theme.space12

        Rectangle {
            Layout.preferredWidth: 34
            Layout.preferredHeight: 34
            radius: Theme.radiusSmall
            color: root.down ? Theme.interactivePressed
                : root.hovered || root.activeFocus ? Theme.interactiveHover : Theme.interactive

            AppIcon {
                anchors.centerIn: parent
                width: 18
                height: 18
                glyph: IconCatalog.glyph(root.iconName)
                iconColor: Theme.textOnAccent
                iconSize: 17
            }
        }

        Text {
            Layout.fillWidth: true
            text: root.text
            color: root.enabled ? Theme.text : Theme.textDisabled
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.body
            font.weight: Font.DemiBold
            textFormat: Text.PlainText
            elide: Text.ElideRight
        }

        FluentIcon {
            Layout.preferredWidth: 14
            Layout.preferredHeight: 14
            name: "forward"
            iconColor: root.enabled ? Theme.textSubtle : Theme.textDisabled
            iconSize: 13
        }
    }

    background: Rectangle {
        radius: Theme.radius
        color: root.down ? Theme.surfaceStrong
            : root.hovered || root.activeFocus ? Theme.surfaceMuted : Theme.surfaceElevated
        border.width: root.activeFocus ? 2 : 1
        border.color: root.activeFocus ? Theme.focus : Theme.outline
    }
}
