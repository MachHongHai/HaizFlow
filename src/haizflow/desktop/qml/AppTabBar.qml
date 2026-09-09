pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Rectangle {
    id: root
    property var tabs: []
    property int currentIndex: 0
    property bool distribute: false
    signal activated(int index)

    implicitHeight: UiMetrics.controlHeight
    color: "transparent"

    RowLayout {
        anchors.fill: parent
        spacing: Theme.space4
        Repeater {
            model: root.tabs
            delegate: Button {
                id: tabButton
                required property int index
                required property var modelData
                Layout.fillWidth: root.distribute
                Layout.fillHeight: true
                Layout.minimumWidth: 108
                leftPadding: Theme.space16
                rightPadding: Theme.space16
                focusPolicy: Qt.TabFocus
                Accessible.role: Accessible.PageTab
                Accessible.name: String(modelData)
                contentItem: Text {
                    text: String(tabButton.modelData)
                    color: tabButton.index === root.currentIndex ? Theme.text : Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.control
                    font.weight: tabButton.index === root.currentIndex ? Font.DemiBold : Font.Normal
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    textFormat: Text.PlainText
                }
                background: Rectangle {
                    color: tabButton.hovered ? Theme.surfaceMuted : "transparent"
                    radius: 0
                    Rectangle {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        height: 2
                        color: tabButton.index === root.currentIndex ? Theme.interactive : "transparent"
                    }
                }
                onClicked: root.activated(index)
            }
        }
    }
}
