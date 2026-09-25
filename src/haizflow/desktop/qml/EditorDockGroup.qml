pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    property var panelIds: []
    property string activePanelId: ""
    readonly property alias contentHost: panelHost

    signal panelActivated(string panelId)

    color: Theme.surface
    border.width: 0

    function panelTitle(panelId) {
        const titles = {
            "tools": qsTr("Công cụ"),
            "properties": qsTr("Thuộc tính"),
            "tasks": qsTr("Tác vụ")
        };
        return titles[panelId] || panelId;
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 32
            visible: root.panelIds.length > 1
            spacing: 0

            Repeater {
                model: root.panelIds
                delegate: StudioButton {
                    required property var modelData
                    text: root.panelTitle(String(modelData))
                    variant: root.activePanelId === String(modelData) ? "secondary" : "ghost"
                    onClicked: root.panelActivated(String(modelData))
                }
            }
            Item { Layout.fillWidth: true }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            visible: root.panelIds.length > 1
            color: Theme.divider
        }

        Item {
            id: panelHost
            Layout.fillWidth: true
            Layout.fillHeight: true
        }
    }

}
