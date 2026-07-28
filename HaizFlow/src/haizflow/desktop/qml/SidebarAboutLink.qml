import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Button {
    id: root

    property bool compact: false

    implicitHeight: 36
    leftPadding: compact ? 0 : 14
    rightPadding: compact ? 0 : 14
    focusPolicy: Qt.TabFocus
    Accessible.name: I18n.t("About & contact")

    contentItem: RowLayout {
        spacing: root.compact ? 0 : 8

        AppIcon {
            visible: root.compact
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: visible ? Theme.iconSmall : 0
            Layout.preferredHeight: visible ? Theme.iconSmall : 0
            glyph: "\uE946"
            iconColor: root.hovered || root.activeFocus ? Theme.interactive : Theme.textSubtle
            iconSize: Theme.iconSmall
        }

        Text {
            Layout.fillWidth: true
            visible: !root.compact
            text: I18n.t("About & contact")
            color: root.hovered || root.activeFocus ? Theme.text : Theme.textMuted
            font.pixelSize: Theme.label
            textFormat: Text.PlainText
            elide: Text.ElideRight
        }
    }

    background: Rectangle {
        radius: Theme.radiusSmall
        color: root.down ? Theme.surfaceStrong : root.hovered ? Theme.surfaceMuted : "transparent"
        border.width: root.activeFocus ? 2 : 0
        border.color: Theme.focus
    }
}
