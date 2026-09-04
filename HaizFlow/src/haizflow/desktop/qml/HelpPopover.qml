pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Button {
    id: root

    property string helpText: ""
    property string accessibleLabel: qsTr("Trợ giúp")

    implicitWidth: 22
    implicitHeight: 22
    padding: 0
    focusPolicy: Qt.TabFocus
    Accessible.name: accessibleLabel
    onClicked: root.openHelp()

    function updateHelpAnchor() {
        const overlay = Overlay.overlay;
        if (!overlay)
            return;
        const point = root.mapToItem(overlay, 0, 0);
        helpPopup.anchorX = point.x;
        helpPopup.anchorY = point.y;
    }

    function openHelp() {
        root.updateHelpAnchor();
        helpPopup.open();
    }

    contentItem: Text {
        text: "?"
        color: root.hovered || helpPopup.opened ? Theme.interactive : Theme.textSubtle
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.label
        font.weight: Font.DemiBold
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        textFormat: Text.PlainText
    }

    background: Rectangle {
        radius: Theme.radiusSmall
        color: root.hovered || helpPopup.opened ? Theme.surfaceMuted : "transparent"
        border.width: root.activeFocus ? 2 : 1
        border.color: root.activeFocus ? Theme.focus : Theme.outline
    }

    Popup {
        id: helpPopup
        objectName: "helpPopoverPopup"

        parent: Overlay.overlay
        property real anchorX: 0
        property real anchorY: 0

        modal: false
        focus: true
        margins: Theme.space8
        width: Math.min(280, Math.max(220, parent.width - Theme.space16))
        x: Math.max(
            Theme.space8,
            Math.min(anchorX + root.width - width, parent.width - width - Theme.space8)
        )
        y: {
            const below = anchorY + root.height + Theme.space4
            if (below + height <= parent.height - Theme.space8)
                return below
            return Math.max(Theme.space8, anchorY - height - Theme.space4)
        }
        padding: Theme.space12
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        onAboutToShow: root.updateHelpAnchor()

        contentItem: ColumnLayout {
            spacing: Theme.space8

            Text {
                Layout.fillWidth: true
                text: root.helpText
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.label
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                maximumLineCount: 5
            }

            StudioButton {
                Layout.alignment: Qt.AlignRight
                text: qsTr("Đóng")
                tone: "ghost"
                onClicked: helpPopup.close()
            }
        }

        background: Rectangle {
            radius: Theme.radius
            color: Theme.surfaceElevated
            border.width: 1
            border.color: Theme.outlineStrong
        }
    }
}
