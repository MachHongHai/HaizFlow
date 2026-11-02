pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import "."

SettingsPageShell {
    id: root
    property var bridge: AppController.mcpBridge
    objectName: "mcpSettingsPage"
    showHeader: false
    pageInset: 0
    horizontalInset: 0
    contentMaximumWidth: 920
    contentSpacing: Theme.space20

    SettingsMcpGroup {
        Layout.fillWidth: true
        bridge: root.bridge
    }
    McpConnectionGuide {
        Layout.fillWidth: true
        bridge: root.bridge
    }
    Item { Layout.preferredHeight: Theme.space8 }
}
