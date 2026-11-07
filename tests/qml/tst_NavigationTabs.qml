pragma ComponentBehavior: Bound
import QtQuick
import QtTest
import "../../src/haizflow/desktop/qml"

Item {
    id: root
    width: 900
    height: 650
    Component {
        id: tabsComponent
        NavigationTabs {
            options: [{label: "Chung", value: "settings"}, {label: "MCP", value: "mcp"}]
            currentValue: "mcp"
            showUnderline: false
            onActivated: function(value) { currentValue = value; }
        }
    }
    TestCase {
        name: "NavigationTabsStyleTests"
        when: windowShown
        function test_settingsSelectionUsesTextOnly() {
            const tabs = createTemporaryObject(tabsComponent, root);
            const active = findChild(tabs, "navigationTab_mcp");
            const inactive = findChild(tabs, "navigationTab_settings");
            compare(active.contentItem.font.weight, Font.DemiBold);
            compare(inactive.contentItem.font.weight, Font.Normal);
            compare(active.background.color.a, 0);
            compare(active.background.border.width, 0);
            mouseMove(active, 10, 10);
            compare(active.background.color.a, 0);
            for (const child of active.background.children) compare(child.visible, false);
        }
        function test_switchKeepsTextOnlyStyle() {
            const tabs = createTemporaryObject(tabsComponent, root);
            const first = findChild(tabs, "navigationTab_settings");
            mouseClick(first, 20, 20);
            compare(tabs.currentValue, "settings");
            compare(first.contentItem.font.weight, Font.DemiBold);
            compare(first.background.color.a, 0);
        }
    }
}
