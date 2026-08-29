pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    property var options: []
    property string currentValue: ""
    signal activated(string value)

    implicitHeight: UiMetrics.controlHeight
    implicitWidth: 240
    radius: Theme.radiusSmall
    color: Theme.input
    border.width: 1
    border.color: Theme.outline
    opacity: enabled ? 1 : 0.55

    RowLayout {
        anchors.fill: parent
        anchors.margins: 3
        spacing: 3

        Repeater {
            model: root.options

            delegate: Button {
                id: optionButton

                required property var modelData
                readonly property bool selected: modelData.value === root.currentValue

                Layout.fillWidth: true
                Layout.fillHeight: true
                enabled: root.enabled
                focusPolicy: Qt.TabFocus
                Accessible.name: modelData.label
                Accessible.role: Accessible.RadioButton
                Accessible.checked: selected

                contentItem: Text {
                    text: optionButton.modelData.label
                    color: optionButton.selected ? Theme.text : Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.label
                    font.weight: optionButton.selected ? Font.DemiBold : Font.Medium
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    textFormat: Text.PlainText
                    elide: Text.ElideNone
                }

                background: Rectangle {
                    radius: Theme.radiusTiny
                    color: optionButton.selected ? Theme.surfaceStrong : optionButton.hovered ? Theme.surfaceMuted : "transparent"
                    border.width: optionButton.activeFocus ? 2 : 0
                    border.color: Theme.focus
                }

                onClicked: root.activated(optionButton.modelData.value)
            }
        }
    }
}
