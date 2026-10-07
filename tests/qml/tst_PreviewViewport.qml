pragma ComponentBehavior: Bound
import QtQuick
import QtTest
import "../../src/haizflow/desktop/qml"

Item {
    id: root
    width: 800
    height: 600

    Component {
        id: viewportComponent
        PreviewViewport {
            width: 500
            height: 300
            onZoomRequested: function(percent) { zoomPercent = percent; }
            property int edits: 0
            property var lastRegion: ({})
            OcrRegionOverlay {
                objectName: "testOcrOverlay"
                anchors.fill: parent
                videoRect: Qt.rect(0, 0, 500, 300)
                region: ({x_percent: 40, y_percent: 40, width_percent: 20, height_percent: 20})
                interactive: true
                editing: true
                onRegionEdited: function(region) {
                    const viewport = parent.parent;
                    viewport.edits++;
                    viewport.lastRegion = region;
                }
            }
        }
    }
    SignalSpy { id: zoomSpy; signalName: "zoomRequested" }
    SignalSpy { id: backgroundTapSpy; signalName: "backgroundTapped" }

    Component {
        id: subtitleViewportComponent
        PreviewViewport {
            width: 500
            height: 300
            zoomPercent: 200
            property int dismissals: 0
            property int edits: 0
            SubtitleTransformOverlay {
                objectName: "testSubtitleOverlay"
                backgroundDismissEnabled: false
                anchors.fill: parent
                videoRect: Qt.rect(0, 0, 500, 300)
                sampleText: qsTr("Subtitle")
                positionYPercent: 50
                interactive: true
                editing: true
                onEditingDismissed: parent.parent.dismissals++
                onLayoutCommitted: parent.parent.edits++
            }
        }
    }
    Component {
        id: watermarkViewportComponent
        PreviewViewport {
            width: 500
            height: 300
            zoomPercent: 200
            property int dismissals: 0
            WatermarkTransformOverlay {
                backgroundDismissEnabled: false
                anchors.fill: parent
                videoRect: Qt.rect(0, 0, 500, 300)
                watermarkText: qsTr("HaizFlow")
                interactive: true
                editing: true
                onEditingDismissed: parent.parent.dismissals++
            }
        }
    }

    TestCase {
        name: "PreviewViewportTests"
        when: windowShown

        function test_zoomKeepsPointUnderCursor() {
            const viewport = createTemporaryObject(viewportComponent, root);
            verify(!!viewport, "Component exists");
            const before = viewport.contentItem.mapFromItem(viewport, 200, 100);
            viewport.zoomAt(200, 100, 200);
            compare(viewport.zoomPercent, 200);
            compare(viewport.contentItem.mapFromItem(viewport, 200, 100), before);
        }

        function test_wheelRequestsZoom() {
            const viewport = createTemporaryObject(viewportComponent, root);
            verify(!!viewport, "Component exists");
            zoomSpy.target = viewport;
            zoomSpy.clear();
            mouseWheel(viewport, 200, 100, 0, 120);
            tryCompare(zoomSpy, "count", 1);
            tryCompare(viewport, "zoomPercent", 100 * Math.pow(1.0015, 120));
        }

        function test_leftDragBackgroundPansButDoesNotEditOcr() {
            const viewport = createTemporaryObject(viewportComponent, root);
            verify(!!viewport, "Component exists");
            viewport.zoomPercent = 200;
            backgroundTapSpy.target = viewport;
            backgroundTapSpy.clear();
            mousePress(viewport, 30, 30);
            tryCompare(viewport, "edits", 0);
            mouseMove(viewport, 80, 50);
            tryCompare(viewport, "panX", 50);
            tryCompare(viewport, "panY", 20);
            mouseRelease(viewport, 80, 50);
            tryCompare(viewport, "edits", 0);
            tryCompare(backgroundTapSpy, "count", 0);
        }

        function test_clickBackgroundDismissesWithoutPanning() {
            const viewport = createTemporaryObject(viewportComponent, root);
            verify(!!viewport, "Component exists");
            backgroundTapSpy.target = viewport;
            backgroundTapSpy.clear();
            mouseClick(viewport, 30, 30);
            tryCompare(backgroundTapSpy, "count", 1);
            tryCompare(viewport, "panX", 0);
            tryCompare(viewport, "edits", 0);
        }

        function test_leftDragOcrEditsButDoesNotPan() {
            const viewport = createTemporaryObject(viewportComponent, root);
            verify(!!viewport, "Component exists");
            viewport.zoomPercent = 200;
            mousePress(viewport, 250, 150);
            tryCompare(viewport, "edits", 0);
            mouseMove(viewport, 300, 150);
            tryCompare(viewport, "panX", 0);
            mouseRelease(viewport, 300, 150);
            tryCompare(viewport, "edits", 1);
            tryCompare(viewport.lastRegion, "x_percent", 45);
            tryCompare(viewport, "panX", 0);
        }

        function test_leftDragOutsideSubtitlePansWithoutDismissing() {
            const viewport = createTemporaryObject(subtitleViewportComponent, root);
            verify(!!viewport, "Component exists");
            mousePress(viewport, 30, 30);
            tryCompare(viewport, "dismissals", 0);
            mouseMove(viewport, 80, 50);
            tryCompare(viewport, "panX", 50);
            mouseRelease(viewport, 80, 50);
            tryCompare(viewport, "dismissals", 0);
            tryCompare(viewport, "edits", 0);
        }

        function test_leftDragSubtitleEditsWithoutPanning() {
            const viewport = createTemporaryObject(subtitleViewportComponent, root);
            verify(!!viewport, "Component exists");
            const selection = findChild(viewport, "subtitleTransformSelection");
            verify(!!selection, "Object exists");
            const point = selection.mapToItem(viewport, selection.width / 2, selection.height / 2);
            mousePress(viewport, point.x, point.y);
            tryCompare(viewport, "edits", 0);
            mouseMove(viewport, point.x + 40, point.y);
            tryCompare(viewport, "panX", 0);
            mouseRelease(viewport, point.x + 40, point.y);
            tryCompare(viewport, "edits", 1);
            tryCompare(viewport, "dismissals", 0);
        }

        function test_leftDragOutsideWatermarkPansWithoutDismissing() {
            const viewport = createTemporaryObject(watermarkViewportComponent, root);
            verify(!!viewport, "Component exists");
            mousePress(viewport, 30, 30);
            tryCompare(viewport, "dismissals", 0);
            mouseMove(viewport, 80, 50);
            tryCompare(viewport, "panX", 50);
            mouseRelease(viewport, 80, 50);
            tryCompare(viewport, "dismissals", 0);
        }

        function test_zoomResetRestoresFitAndPanBounds() {
            const viewport = createTemporaryObject(viewportComponent, root);
            verify(!!viewport, "Component exists");
            viewport.zoomAt(10, 10, 1000);
            compare(viewport.zoomPercent, 400);
            viewport.panX = 2000;
            viewport.panY = -2000;
            viewport.clampPan();
            compare(viewport.panX, 750);
            compare(viewport.panY, -450);
            viewport.zoomAt(250, 150, 100);
            compare(viewport.panX, 0);
            compare(viewport.panY, 0);
        }
    }
}
