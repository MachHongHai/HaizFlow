pragma ComponentBehavior: Bound
import QtQuick
import QtTest
import "../../src/haizflow/desktop/qml"

Item {
    id: root
    width: 640
    height: 480

    Component {
        id: overlayComponent
        OcrRegionOverlay {
            width: 600
            height: 400
            videoRect: Qt.rect(50, 50, 500, 300)
            interactive: true
            editing: true
            region: ({x_percent: 20, y_percent: 50, width_percent: 60, height_percent: 20})
        }
    }

    SignalSpy { id: commitSpy; signalName: "regionEdited" }
    SignalSpy { id: startSpy; signalName: "editingStarted" }

    TestCase {
        name: "OcrRegionOverlayTests"
        when: windowShown

        function test_editingStartedOnPress() {
            const overlay = createTemporaryObject(overlayComponent, root);
            verify(!!overlay, "Component exists");
            startSpy.target = overlay;
            startSpy.clear();
            mousePress(overlay, 300, 230);
            tryCompare(startSpy, "count", 1);
            mouseRelease(overlay, 300, 230);
            tryCompare(overlay, "draft", null);
        }

        function test_dragCommitsOnlyOnRelease() {
            const overlay = createTemporaryObject(overlayComponent, root);
            verify(!!overlay, "Component exists");
            commitSpy.target = overlay;
            commitSpy.clear();
            mousePress(overlay, 300, 230);
            tryCompare(commitSpy, "count", 0);
            mouseMove(overlay, 350, 260);
            tryCompare(overlay.currentRegion, "x_percent", 30);
            tryCompare(overlay.currentRegion, "y_percent", 60);
            tryCompare(commitSpy, "count", 0);
            mouseRelease(overlay, 350, 260);
            tryCompare(commitSpy, "count", 1);
            tryCompare(commitSpy.signalArguments[0][0], "x_percent", 30);
            tryCompare(commitSpy.signalArguments[0][0], "y_percent", 60);
            tryCompare(overlay.region, "x_percent", 20);
            tryCompare(overlay, "draft", null);
        }

        function test_resizeCommitsOnlyOnRelease() {
            const overlay = createTemporaryObject(overlayComponent, root);
            verify(!!overlay, "Component exists");
            const handle = findChild(overlay, "subtitleBoxHandle_1_1");
            verify(!!handle, "Object exists");
            commitSpy.target = overlay;
            commitSpy.clear();
            mousePress(handle, handle.width / 2, handle.height / 2);
            tryCompare(handle, "pressed", true);
            mouseMove(overlay, 500, 290);
            tryCompare(overlay.currentRegion, "width_percent", 70);
            tryCompare(overlay.currentRegion, "height_percent", 30);
            tryCompare(commitSpy, "count", 0);
            mouseRelease(overlay, 500, 290);
            tryCompare(commitSpy, "count", 1);
            tryCompare(commitSpy.signalArguments[0][0], "width_percent", 70);
            tryCompare(commitSpy.signalArguments[0][0], "height_percent", 30);
        }

        function test_dragClampsAtVideoBoundary() {
            const overlay = createTemporaryObject(overlayComponent, root);
            verify(!!overlay, "Component exists");
            commitSpy.target = overlay;
            commitSpy.clear();
            mousePress(overlay, 300, 230);
            tryCompare(commitSpy, "count", 0);
            mouseMove(overlay, -10, -10);
            tryCompare(overlay.currentRegion, "x_percent", 0);
            tryCompare(overlay.currentRegion, "y_percent", 0);
            mouseRelease(overlay, -10, -10);
            tryCompare(commitSpy, "count", 1);
            tryCompare(commitSpy.signalArguments[0][0], "x_percent", 0);
            tryCompare(commitSpy.signalArguments[0][0], "y_percent", 0);
        }
    }
}
