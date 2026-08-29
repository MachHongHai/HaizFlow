import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

MenuItem {
    id: root

    property string iconGlyph: ""
    property string tone: "normal"
    property bool collapsed: false

    visible: !collapsed
    implicitWidth: collapsed ? 0 : menuContent.implicitWidth + leftPadding + rightPadding
    implicitHeight: collapsed ? 0 : 34
    leftPadding: 11
    rightPadding: 11
    activeFocusOnTab: true
    Accessible.name: text

    contentItem: RowLayout {
        id: menuContent

        spacing: menuIcon.visible ? 10 : 0
        implicitWidth: (menuIcon.visible ? Theme.icon : 0) + spacing + menuLabel.implicitWidth
        implicitHeight: Math.max(menuIcon.implicitHeight, menuLabel.implicitHeight)

        AppIcon {
            id: menuIcon
            visible: root.iconGlyph.length > 0
            Layout.preferredWidth: visible ? Theme.icon : 0
            Layout.preferredHeight: 22
            glyph: root.iconGlyph
            iconColor: !root.enabled ? Theme.textDisabled : root.tone === "danger" ? Theme.danger : Theme.textMuted
            iconSize: Theme.iconSmall
        }

        Text {
            id: menuLabel
            objectName: "menuItemLabel"
            Layout.fillWidth: true
            Layout.preferredHeight: 22
            text: root.text
            color: !root.enabled ? Theme.textDisabled : root.tone === "danger" ? Theme.danger : Theme.text
            font.pixelSize: Theme.caption
            font.weight: Font.Medium
            verticalAlignment: Text.AlignVCenter
            textFormat: Text.PlainText
            elide: Text.ElideRight
        }
    }

    background: Rectangle {
        radius: Theme.radiusSmall
        color: root.highlighted ? (root.tone === "danger" ? Theme.dangerMuted : Theme.surfaceMuted) : "transparent"
    }
}
