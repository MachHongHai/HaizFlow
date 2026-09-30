pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

Item {
    id: root
    required property string currentRoute
    signal navigateRequested(string route)
    onVisibleChanged: AppController.setHardwareTelemetryActive(visible)
    Component.onCompleted: AppController.setHardwareTelemetryActive(visible)

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: UiMetrics.pageMargin
        spacing: Theme.space12

        PageHeader {
            Layout.fillWidth: true
            title: qsTr("Cài đặt")
        }
        SegmentedControl {
            Layout.preferredWidth: 390
            currentValue: root.currentRoute
            options: [
                { label: qsTr("Chung"), value: "settings" },
                { label: qsTr("API Key"), value: "api-keys" },
                { label: qsTr("Gói tài nguyên"), value: "packages" }
            ]
            onActivated: function(value) { root.navigateRequested(value); }
        }
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.divider
        }
        StackLayout {
            id: settingsPages
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: root.currentRoute === "api-keys" ? 1
                : root.currentRoute === "packages" ? 2 : 0
            SettingsPage { Layout.fillWidth: true; Layout.fillHeight: true }
            ApiKeysPage { Layout.fillWidth: true; Layout.fillHeight: true }
            Loader {
                Layout.fillWidth: true
                Layout.fillHeight: true
                active: settingsPages.currentIndex === 2
                asynchronous: true
                sourceComponent: Component { ResourcePacksPage {} }
            }
        }
    }
}
