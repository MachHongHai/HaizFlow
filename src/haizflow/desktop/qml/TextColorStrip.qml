pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root

    property string label: ""
    property string selectedColor: "#FFFFFF"
    property var colors: ["#FFFFFF", "#000000", "#FFEF00", "#EF5350", "#66BB6A", "#42A5F5", "#FF9C55"]
    signal colorSelected(string value)

    spacing: Theme.space4

    SettingLabel {
        Layout.fillWidth: true
        text: root.label
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 2

        Repeater {
            model: root.colors
            delegate: Button {
                id: swatch
                required property string modelData
                Layout.preferredWidth: 28
                Layout.preferredHeight: 30
                focusPolicy: Qt.TabFocus
                Accessible.name: qsTr("%1 · %2").arg(root.label).arg(modelData)
                onClicked: root.colorSelected(modelData)
                background: Item {
                    Rectangle {
                        anchors.centerIn: parent
                        width: 22
                        height: 22
                        radius: Theme.radiusTiny
                        color: swatch.modelData
                        border.width: root.selectedColor.toUpperCase() === swatch.modelData ? 3 : 1
                        border.color: swatch.activeFocus ? Theme.focus : Theme.outlineStrong
                    }
                }
            }
        }

        Button {
            id: customColorButton
            objectName: "customColorButton"
            Layout.preferredWidth: 30
            Layout.preferredHeight: 30
            focusPolicy: Qt.TabFocus
            Accessible.name: qsTr("Chọn màu RGB cho %1").arg(root.label)
            onClicked: colorPicker.open()
            contentItem: Text {
                text: "+"
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.control
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
            background: Rectangle {
                radius: Theme.radiusTiny
                color: Theme.surfaceElevated
                border.width: customColorButton.activeFocus ? 2 : 1
                border.color: customColorButton.activeFocus ? Theme.focus : Theme.outlineStrong
            }
        }
        Item { Layout.fillWidth: true }
    }

    ColorPickerPopup {
        id: colorPicker
        objectName: "rgbColorPopup"
        parent: Overlay.overlay
        currentColor: root.selectedColor
        onColorApplied: function(value) { root.colorSelected(value) }
    }
}
