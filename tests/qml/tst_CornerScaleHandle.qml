pragma ComponentBehavior: Bound

import QtQuick
import QtTest

import "../../src/haizflow/desktop/qml"

Item {
    id: root
    width: 640
    height: 480

    Item {
        id: coordinateSpace
        anchors.fill: parent

        Item {
            id: selection
            x: 180
            y: 120
            width: 160
            height: 90
        }
    }

    Component {
        id: handleComponent

        CornerScaleHandle {
            selectionItem: selection
            coordinateItem: coordinateSpace
            horizontalDirection: 1
            verticalDirection: 1
            currentValue: 100
            minimumValue: 10
            maximumValue: 300
        }
    }

    SignalSpy {
        id: resizeStartedSpy
        signalName: "resizeStarted"
    }

    SignalSpy {
        id: previewSpy
        signalName: "valuePreviewed"
    }

    SignalSpy {
        id: commitSpy
        signalName: "valueCommitted"
    }

    TestCase {
        name: "CornerScaleHandleTests"
        when: windowShown

        function test_defaultRange() {
            let handle = createTemporaryObject(handleComponent, root)
            verify(!!handle, "Component exists")
            compare(handle.currentValue, 100)
            compare(handle.minimumValue, 10)
            compare(handle.maximumValue, 300)
            compare(handle.pressed, false)
        }

        function test_dragPreviewsAndCommitsOneResize() {
            let handle = createTemporaryObject(handleComponent, root)
            verify(!!handle, "Component exists")
            resizeStartedSpy.target = handle
            previewSpy.target = handle
            commitSpy.target = handle
            resizeStartedSpy.clear()
            previewSpy.clear()
            commitSpy.clear()

            mousePress(handle, handle.width / 2, handle.height / 2)
            tryCompare(resizeStartedSpy, "count", 1)
            tryCompare(handle, "pressed", true)

            mouseMove(handle, handle.width / 2 + 36, handle.height / 2 + 36)
            tryCompare(previewSpy, "count", 1)
            verify(handle.previewValue > handle.currentValue)

            mouseRelease(handle, handle.width / 2 + 36, handle.height / 2 + 36)
            tryCompare(commitSpy, "count", 1)
            tryCompare(handle, "pressed", false)
        }

        function test_dragClampsAtMaximum() {
            let handle = createTemporaryObject(handleComponent, root)
            verify(!!handle, "Component exists")
            previewSpy.target = handle
            previewSpy.clear()

            mousePress(handle, handle.width / 2, handle.height / 2)
            tryCompare(handle, "pressed", true)
            mouseMove(handle, handle.width / 2 + 1000, handle.height / 2 + 1000)
            tryCompare(previewSpy, "count", 1)
            compare(handle.previewValue, 300)
            mouseRelease(handle, handle.width / 2 + 1000, handle.height / 2 + 1000)
            tryCompare(handle, "pressed", false)
        }
    }
}
