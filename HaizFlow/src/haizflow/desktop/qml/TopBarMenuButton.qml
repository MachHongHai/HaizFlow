import QtQuick
import QtQuick.Controls.Basic
import "."

Button {
    id: root

    property bool menuWasOpenOnPress: false

    implicitHeight: 28
    leftPadding: 10
    rightPadding: 10
    topPadding: 0
    bottomPadding: 0
    focusPolicy: Qt.TabFocus
    Accessible.name: text

    contentItem: Text {
        text: root.text
        color: root.enabled
            ? (root.hovered || root.down ? Theme.text : Theme.textMuted)
            : Theme.textDisabled
        font.family: Theme.fontFamily
        font.pixelSize: Theme.caption
        font.weight: Font.Normal
        verticalAlignment: Text.AlignVCenter
        textFormat: Text.PlainText
    }

    background: Rectangle {
        radius: Theme.radiusSmall
        color: root.down ? Theme.windowCaptionPressed
            : root.hovered || root.activeFocus ? Theme.windowCaptionHover : "transparent"
        border.width: 0
    }
}
