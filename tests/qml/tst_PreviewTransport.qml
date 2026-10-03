import QtQuick
import QtTest
import "../../src/haizflow/desktop/qml"

Item {
    id: root
    width: 900
    height: 200
    Component {
        id: transportComponent
        PreviewTransport { width: 800; height: 48; duration: 100; showFullscreen: false }
    }
    SignalSpy { id: finishedSpy; signalName: "scrubFinished" }
    SignalSpy { id: startedSpy; signalName: "scrubStarted" }
    TestCase {
        name: "PreviewTransportScrubTests"
        when: windowShown
        function test_decoderPositionDoesNotOverrideHeldThumb() {
            const transport = createTemporaryObject(transportComponent, root);
            verify(!!transport);
            finishedSpy.target = transport;
            finishedSpy.clear();
            startedSpy.target = transport;
            startedSpy.clear();
            mousePress(transport, 300, 24);
            tryCompare(startedSpy, "count", 1);
            mouseMove(transport, 600, 24);
            transport.position = 2;
            mouseRelease(transport, 600, 24);
            tryCompare(finishedSpy, "count", 1);
            verify(finishedSpy.signalArguments[0][0] > 60,
                   "A stale decoder position must not pull a dragged thumb back to the start");
        }
    }
}
