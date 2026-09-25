pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root

    property var tools: []
    property int currentIndex: 0
    signal toolSelected(int index)

    ListView {
        id: toolList
        anchors.fill: parent
        anchors.margins: Theme.space8
        clip: true
        spacing: 2
        model: root.tools

        delegate: Rectangle {
            id: row
            required property int index
            required property var modelData
            width: toolList.width
            height: 40
            color: root.currentIndex === index ? Theme.sidebarSelected
                : pointer.hovered ? Theme.surfaceMuted : "transparent"
            radius: Theme.radiusTiny

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.space8
                anchors.rightMargin: Theme.space8
                spacing: Theme.space8

                Text {
                    Layout.fillWidth: true
                    text: String(row.modelData.label || "")
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.control
                    elide: Text.ElideRight
                }
                Text {
                    visible: String(row.modelData.state || "") === "processing"
                        || String(row.modelData.state || "") === "error"
                    text: String(row.modelData.state || "") === "error"
                        ? qsTr("Lỗi") : qsTr("Đang chạy")
                    color: String(row.modelData.state || "") === "error"
                        ? Theme.danger : Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.metadata
                }
            }

            HoverHandler { id: pointer }
            TapHandler { onTapped: root.toolSelected(row.index) }
        }
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
    }
}
