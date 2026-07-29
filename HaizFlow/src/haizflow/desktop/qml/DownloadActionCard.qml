import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Button {
    id: root

    property string subtitle: ""

    Layout.fillWidth: true
    Layout.minimumWidth: 0
    Layout.preferredWidth: 1
    Layout.minimumHeight: 104
    Layout.preferredHeight: 112
    leftPadding: Theme.space12
    rightPadding: Theme.space12
    topPadding: Theme.space12
    bottomPadding: Theme.space12
    focusPolicy: Qt.TabFocus
    Accessible.name: text
    Accessible.description: subtitle

    contentItem: ColumnLayout {
        spacing: Theme.space8

        Text {
            Layout.fillWidth: true
            text: root.text
            color: Theme.text
            font.pixelSize: Theme.bodyLarge
            font.weight: Font.DemiBold
            textFormat: Text.PlainText
            elide: Text.ElideRight
            maximumLineCount: 1
            wrapMode: Text.NoWrap
        }

        Text {
            Layout.fillWidth: true
            text: root.subtitle
            color: Theme.textMuted
            font.pixelSize: Theme.body
            textFormat: Text.PlainText
            elide: Text.ElideRight
            maximumLineCount: 2
            wrapMode: Text.WordWrap
        }
    }

    background: Rectangle {
        radius: Theme.radius
        color: root.down ? Theme.surfaceStrong : root.hovered ? Theme.surfaceMuted : Theme.surface
        border.width: root.activeFocus ? 2 : 1
        border.color: root.activeFocus ? Theme.focus : Theme.outline

        Behavior on color { ColorAnimation { duration: Theme.motionFast } }
    }
}
