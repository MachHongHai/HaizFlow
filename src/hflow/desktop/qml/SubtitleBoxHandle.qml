pragma ComponentBehavior: Bound
import QtQuick
import "."

Item {
    id: root
    required property Item selectionItem
    required property Item canvasItem
    required property int horizontalDirection
    required property int verticalDirection
    readonly property bool pressed: area.pressed
    property rect initialRect
    property point initialPointer
    property rect previewRect
    property real minimumWidthPixels: 24
    property real maximumWidthPixels: canvasItem ? canvasItem.width : 0
    property real minimumHeightPixels: 4
    property real maximumHeightPixels: canvasItem ? canvasItem.height : 0
    signal rectanglePreviewed(rect rectangle)
    signal rectangleCommitted(rect rectangle)
    signal resizeStarted()
    signal resizeCanceled()
    objectName: "subtitleBoxHandle_" + horizontalDirection + "_" + verticalDirection
    width: horizontalDirection !== 0 ? 28 : Math.max(8, Math.min(28, selectionItem.width * 0.4))
    height: verticalDirection !== 0 ? 28 : Math.max(8, Math.min(28, selectionItem.height * 0.4))
    x: horizontalDirection < 0 ? -width / 2
        : horizontalDirection > 0 ? selectionItem.width - width / 2 : (selectionItem.width - width) / 2
    y: verticalDirection < 0 ? -height / 2
        : verticalDirection > 0 ? selectionItem.height - height / 2 : (selectionItem.height - height) / 2
    z: 7
    activeFocusOnTab: visible
    Accessible.role: Accessible.Slider
    Accessible.name: horizontalDirection !== 0 ? qsTr("Chiều rộng phụ đề") : qsTr("Chiều cao phụ đề")

    function begin(point) {
        initialRect = Qt.rect(selectionItem.x, selectionItem.y, selectionItem.width, selectionItem.height);
        initialPointer = point;
        previewRect = initialRect;
        resizeStarted();
    }
    function update(point) {
        let left = initialRect.x;
        let right = left + initialRect.width;
        let top = initialRect.y;
        let bottom = top + initialRect.height;
        const minWidth = minimumWidthPixels;
        const minHeight = minimumHeightPixels;
        const dx = point.x - initialPointer.x;
        const dy = point.y - initialPointer.y;
        if (horizontalDirection < 0) left = Math.max(0, right - maximumWidthPixels, Math.min(right - minWidth, left + dx));
        if (horizontalDirection > 0) right = Math.min(canvasItem.width, left + maximumWidthPixels, Math.max(left + minWidth, right + dx));
        if (verticalDirection < 0) top = Math.max(0, bottom - maximumHeightPixels, Math.min(bottom - minHeight, top + dy));
        if (verticalDirection > 0) bottom = Math.min(canvasItem.height, top + maximumHeightPixels, Math.max(top + minHeight, bottom + dy));
        previewRect = Qt.rect(left, top, right - left, bottom - top);
        rectanglePreviewed(previewRect);
    }
    Keys.onPressed: function(event) {
        const step = event.modifiers & Qt.ShiftModifier ? 10 : 2;
        let dx = 0;
        let dy = 0;
        if (horizontalDirection !== 0 && event.key === Qt.Key_Left) dx = -step;
        else if (horizontalDirection !== 0 && event.key === Qt.Key_Right) dx = step;
        else if (verticalDirection !== 0 && event.key === Qt.Key_Up) dy = -step;
        else if (verticalDirection !== 0 && event.key === Qt.Key_Down) dy = step;
        else return;
        begin(Qt.point(0, 0));
        update(Qt.point(dx, dy));
        rectangleCommitted(previewRect);
        event.accepted = true;
    }
    Rectangle {
        anchors.centerIn: parent
        width: root.horizontalDirection !== 0 ? 7 : 18
        height: root.horizontalDirection !== 0 ? Math.min(18, root.height - 2) : 7
        radius: 2
        color: root.activeFocus ? Theme.text : Theme.focus
        border.width: 1
        border.color: Theme.surface
        Accessible.ignored: true
    }
    MouseArea {
        id: area
        anchors.fill: parent
        preventStealing: true
        hoverEnabled: true
        cursorShape: root.horizontalDirection !== 0 ? Qt.SizeHorCursor : Qt.SizeVerCursor
        onPressed: function(mouse) { root.begin(mapToItem(root.canvasItem, mouse.x, mouse.y)); }
        onPositionChanged: function(mouse) {
            if (pressed) root.update(mapToItem(root.canvasItem, mouse.x, mouse.y));
        }
        onReleased: root.rectangleCommitted(root.previewRect)
        onCanceled: root.resizeCanceled()
    }
    HoverHandler { cursorShape: root.horizontalDirection !== 0 ? Qt.SizeHorCursor : Qt.SizeVerCursor }
}
