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
    onClicked: helpPopup.open()

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

        x: Math.max(-root.mapToItem(null, 0, 0).x + Theme.space8, root.width - width)
        y: root.height + Theme.space4
        width: 280
        padding: Theme.space12
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent

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
