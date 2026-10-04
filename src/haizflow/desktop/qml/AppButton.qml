import QtQuick
import QtQuick.Controls.Basic
import "."

Button {
    id: root

    property string tone: "secondary"
    property bool compact: false
    property string iconGlyph: ""
    property string toolTipText: ""
    property bool showToolTip: false
    readonly property bool showLeadingIcon: iconGlyph.length > 0 && text.length === 0

    implicitHeight: compact ? UiMetrics.compactControlHeight : tone === "primary" ? UiMetrics.primaryControlHeight : UiMetrics.controlHeight
    implicitWidth: Math.max(compact ? 64 : 80, buttonContent.implicitWidth + leftPadding + rightPadding)
    leftPadding: compact ? 10 : 12
    rightPadding: compact ? 10 : 12
    font.family: Theme.fontFamily
    font.pixelSize: TypeScale.control
    font.weight: Font.DemiBold
    focusPolicy: Qt.TabFocus
    Accessible.name: text.length > 0 ? text : toolTipText
    Accessible.description: toolTipText
    scale: down ? 0.98 : 1

    readonly property color foregroundColor: !enabled ? Theme.textDisabled : tone === "primary" ? Theme.textOnAccent : tone === "danger" ? Theme.danger : Theme.text

    contentItem: Item {
        implicitWidth: buttonContent.implicitWidth
        implicitHeight: Math.max(buttonContent.implicitHeight, Theme.icon)

        Row {
            id: buttonContent
            anchors.centerIn: parent
            spacing: 0

            AppIcon {
                objectName: "buttonLeadingIcon"
                width: root.showLeadingIcon ? Theme.icon : 0
                height: parent.height
                visible: root.showLeadingIcon
                glyph: root.iconGlyph
                iconColor: root.foregroundColor
                iconSize: root.compact ? Theme.iconSmall : Theme.icon
            }

            Text {
                height: Math.max(20, implicitHeight)
                text: root.text
                color: root.foregroundColor
                font: root.font
                verticalAlignment: Text.AlignVCenter
                textFormat: Text.PlainText
                elide: Text.ElideNone
            }
        }
    }

    background: Rectangle {
        id: buttonBackground
        radius: Theme.radiusSmall
        color: !root.enabled ? Theme.surfaceMuted : root.tone === "primary" ? (root.down ? Theme.interactivePressed : root.hovered ? Theme.interactiveHover : Theme.interactive) : root.tone === "ghost" ? (root.down ? Theme.surfaceStrong : root.hovered ? Theme.surfaceMuted : "transparent") : root.tone === "danger" ? (root.down || root.hovered ? Theme.dangerMuted : "transparent") : root.down ? Theme.surfaceStrong : root.hovered ? Theme.surfaceMuted : Theme.surfaceElevated
        border.width: root.visualFocus ? 2 : root.tone === "primary" ? 0 : 1
        border.color: root.visualFocus ? Theme.focus : root.tone === "danger" ? Theme.danger : Theme.outline
    }

    Behavior on scale {
        NumberAnimation {
            duration: Theme.motionFast
            easing.type: Easing.OutCubic
        }
    }

    ToolTip.visible: root.showToolTip && hovered && !down && toolTipText.length > 0
    ToolTip.text: toolTipText
    ToolTip.delay: 500
}
