import QtQuick
import QtQuick.Controls.Basic
import "."

Button {
    id: root

    property string glyph: ""
    property string toolTipText: ""
    property bool menuWasOpenOnPress: false

    implicitWidth: 28
    implicitHeight: 28
    leftPadding: 0
    rightPadding: 0
    topPadding: 0
    bottomPadding: 0
    focusPolicy: Qt.TabFocus
    Accessible.name: toolTipText
    ToolTip.visible: hovered && toolTipText.length > 0
    ToolTip.text: toolTipText
    ToolTip.delay: 450

    contentItem: AppIcon {
        glyph: root.glyph
        iconSize: 14
        iconColor: root.enabled
            ? (root.hovered || root.down ? Theme.text : Theme.textMuted)
            : Theme.textDisabled
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }

    background: Rectangle {
        radius: Theme.radiusSmall
        color: root.down ? Theme.windowCaptionPressed
            : root.hovered || root.activeFocus ? Theme.windowCaptionHover : "transparent"
        border.width: 0
    }
}
