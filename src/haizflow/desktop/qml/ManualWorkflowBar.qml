pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    property int selectedTool: 0
    property var toolModel: []
    property bool hasVideo: false
    signal toolSelected(int index)

    implicitHeight: 44
    color: Theme.surface
    border.width: 1
    border.color: Theme.divider
    radius: Theme.radiusSmall

    RowLayout {
        anchors.fill: parent
        anchors.margins: Theme.space4
        spacing: Theme.space4

        Repeater {
            model: root.toolModel

            delegate: Rectangle {
                id: toolButton
                required property int index
                required property var modelData

                readonly property bool selected: root.selectedTool === index
                readonly property string toolState: String(modelData.state || "blocked")

                Layout.fillWidth: true
                Layout.minimumWidth: 86
                Layout.preferredHeight: 34
                radius: Theme.radiusTiny
                color: selected ? Theme.sidebarSelected
                    : toolHover.hovered ? Theme.surfaceMuted : "transparent"
                border.width: activeFocus ? 2 : 0
                border.color: Theme.focus
                enabled: root.hasVideo
                activeFocusOnTab: true
                Accessible.role: Accessible.Button
                Accessible.name: String(modelData.label || "")

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: Theme.space8
                    anchors.rightMargin: Theme.space8
                    spacing: Theme.space8

                    Rectangle {
                        Layout.preferredWidth: 6
                        Layout.preferredHeight: 6
                        radius: 3
                        color: toolButton.toolState === "running" ? Theme.warning
                            : toolButton.toolState === "error" ? Theme.danger
                            : toolButton.toolState === "cached" ? Theme.success
                            : toolButton.toolState === "ready" ? Theme.interactive
                            : Theme.textDisabled
                    }

                    Text {
                        Layout.fillWidth: true
                        text: String(toolButton.modelData.label || "")
                        color: toolButton.enabled ? Theme.text : Theme.textDisabled
                        font.family: Theme.fontFamily
                        font.pixelSize: TypeScale.control
                        font.weight: toolButton.selected ? Font.DemiBold : Font.Normal
                        textFormat: Text.PlainText
                        horizontalAlignment: Text.AlignHCenter
                        elide: Text.ElideRight
                    }
                }

                HoverHandler {
                    id: toolHover
                    cursorShape: toolButton.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                }
                TapHandler {
                    enabled: toolButton.enabled
                    onTapped: root.toolSelected(toolButton.index)
                }
                Keys.onReturnPressed: root.toolSelected(toolButton.index)
                Keys.onSpacePressed: root.toolSelected(toolButton.index)
            }
        }
    }
}
