pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

Item {
    id: root
    required property string currentRoute
    signal navigateRequested(string route)
    readonly property bool telemetryNeeded: visible && (currentRoute === "settings" || currentRoute === "packages")
    onTelemetryNeededChanged: AppController.setHardwareTelemetryActive(telemetryNeeded)
    Component.onDestruction: AppController.setHardwareTelemetryActive(false)

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: UiMetrics.pageMargin
        spacing: Theme.space12

        PageHeader {
            Layout.fillWidth: true
            Layout.maximumWidth: 920
            Layout.alignment: Qt.AlignHCenter
            title: qsTr("Cài đặt")
        }
        Item {
            Layout.fillWidth: true
            Layout.maximumWidth: 920
            Layout.alignment: Qt.AlignHCenter
            implicitHeight: tabs.implicitHeight
            NavigationTabs {
                id: tabs
                showUnderline: false
                anchors.left: parent.left
                currentValue: root.currentRoute
                options: [
                    { label: qsTr("Chung"), value: "settings" },
                    { label: qsTr("API Key"), value: "api-keys" },
                    { label: qsTr("Gói tài nguyên"), value: "packages" },
                    { label: qsTr("MCP"), value: "mcp" }
                ]
                onActivated: function(value) { root.navigateRequested(value); }
            }
        }
        StackLayout {
            id: settingsPages
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: root.currentRoute === "api-keys" ? 1
                : root.currentRoute === "packages" ? 2 : root.currentRoute === "mcp" ? 3 : 0
            SettingsPageLoader {
                Layout.fillWidth: true
                Layout.fillHeight: true
                selected: settingsPages.currentIndex === 0
                workspaceVisible: root.visible
                sourceComponent: Component { SettingsPage {} }
            }
            SettingsPageLoader {
                Layout.fillWidth: true
                Layout.fillHeight: true
                selected: settingsPages.currentIndex === 1
                workspaceVisible: root.visible
                sourceComponent: Component { ApiKeysPage {} }
            }
            SettingsPageLoader {
                Layout.fillWidth: true
                Layout.fillHeight: true
                selected: settingsPages.currentIndex === 2
                workspaceVisible: root.visible
                sourceComponent: Component { ResourcePacksPage {} }
            }
            SettingsPageLoader {
                Layout.fillWidth: true
                Layout.fillHeight: true
                selected: settingsPages.currentIndex === 3
                workspaceVisible: root.visible
                sourceComponent: Component { McpSettingsPage {} }
            }
        }
    }
}
