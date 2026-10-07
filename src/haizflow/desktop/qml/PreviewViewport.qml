pragma ComponentBehavior: Bound
import QtQuick

Item {
    id: root
    default property alias contentData: scene.data
    property real zoomPercent: 100
    readonly property real zoomFactor: Math.max(0.5, Math.min(4, zoomPercent / 100))
    property real panX: 0
    property real panY: 0
    property point panStart
    property point pointerStart
    signal zoomRequested(real percent)
    signal backgroundTapped()
    clip: true

    function clampPan() {
        const limitX = Math.max(0, (zoomFactor - 1) * width / 2);
        const limitY = Math.max(0, (zoomFactor - 1) * height / 2);
        panX = Math.max(-limitX, Math.min(limitX, panX));
        panY = Math.max(-limitY, Math.min(limitY, panY));
    }
    function zoomAt(x, y, percent) {
        const next = Math.max(50, Math.min(400, percent));
        const ratio = next / 100 / zoomFactor;
        panX = x - width / 2 - (x - width / 2 - panX) * ratio;
        panY = y - height / 2 - (y - height / 2 - panY) * ratio;
        zoomRequested(next);
        clampPan();
    }
    onZoomFactorChanged: clampPan()
    onWidthChanged: clampPan()
    onHeightChanged: clampPan()

    readonly property Item contentItem: Item {
        id: scene
        parent: root
        width: root.width
        height: root.height
        x: root.panX
        y: root.panY
        scale: root.zoomFactor
        transformOrigin: Item.Center
    }

    WheelHandler {
        parent: root
        target: null
        onWheel: function(event) {
            const delta = event.angleDelta.y || event.pixelDelta.y;
            if (!delta)
                return;
            root.zoomAt(event.x, event.y, root.zoomPercent * Math.pow(1.0015, delta));
            event.accepted = true;
        }
    }
    MouseArea {
        id: panArea
        parent: root
        anchors.fill: parent
        z: -1
        acceptedButtons: Qt.LeftButton | Qt.MiddleButton
        preventStealing: true
        property bool moved: false
        cursorShape: pressed ? Qt.ClosedHandCursor : root.zoomFactor > 1 ? Qt.OpenHandCursor : Qt.ArrowCursor
        onPressed: function(mouse) {
            moved = false;
            root.panStart = Qt.point(root.panX, root.panY);
            root.pointerStart = Qt.point(mouse.x, mouse.y);
        }
        onPositionChanged: function(mouse) {
            if (!pressed)
                return;
            if (Math.abs(mouse.x - root.pointerStart.x) + Math.abs(mouse.y - root.pointerStart.y)
                    > panArea.drag.threshold)
                moved = true;
            root.panX = root.panStart.x + mouse.x - root.pointerStart.x;
            root.panY = root.panStart.y + mouse.y - root.pointerStart.y;
            root.clampPan();
        }
        onDoubleClicked: root.zoomAt(root.width / 2, root.height / 2, 100)
        onClicked: function(mouse) {
            if (!moved && mouse.button === Qt.LeftButton)
                root.backgroundTapped();
        }
    }
}
