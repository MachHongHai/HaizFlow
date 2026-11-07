pragma ComponentBehavior: Bound
import QtQuick
import QtTest
import "../../src/haizflow/desktop/qml"

Item {
    id: root
    width: 900
    height: 650
    property int created: 0
    Component {
        id: loaderComponent
        SettingsPageLoader {
            sourceComponent: Component { Item { Component.onCompleted: root.created += 1 } }
        }
    }
    TestCase {
        name: "SettingsPageLoaderTests"
        when: windowShown
        function test_retainsVisitedTabButReleasesOnLeavingSettings() {
            root.created = 0;
            const loader = createTemporaryObject(loaderComponent, root);
            loader.workspaceVisible = true;
            compare(loader.active, false);
            loader.selected = true;
            tryCompare(loader, "status", Loader.Ready);
            compare(root.created, 1);
            const first = loader.item;
            loader.selected = false;
            compare(loader.active, true);
            compare(loader.item, first);
            loader.selected = true;
            compare(loader.item, first);
            compare(root.created, 1);
            loader.workspaceVisible = false;
            tryCompare(loader, "item", null);
            compare(loader.visited, false);
            loader.selected = false;
            loader.workspaceVisible = true;
            compare(loader.active, false);
            loader.selected = true;
            tryCompare(loader, "status", Loader.Ready);
            compare(root.created, 2);
        }
    }
}
