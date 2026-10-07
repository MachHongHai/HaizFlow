pragma ComponentBehavior: Bound
import QtQuick
import "."

Item {
    id: root
    property rect videoRect: Qt.rect(0, 0, width, height)
    property rect sourceFramePercent: Qt.rect(0, 0, 100, 100)
    property var region: ({})
    property bool interactive: false
    property bool editing: false
    property var draft: null
    property rect startRect
    property point startPointer
    readonly property var currentRegion: draft || region
    signal editingStarted()
    signal regionEdited(var region)
    visible: interactive && Number(region.width_percent || 0) > 0 && videoRect.width > 0

    function preview(rectangle) {
        draft = {x_percent: rectangle.x * 100 / canvas.width,
            y_percent: rectangle.y * 100 / canvas.height,
            width_percent: rectangle.width * 100 / canvas.width,
            height_percent: rectangle.height * 100 / canvas.height};
    }
    function finishEdit(rectangle) {
        preview(rectangle);
        if (["x_percent", "y_percent", "width_percent", "height_percent"].some(function(key) {
                return Math.abs(Number(root.draft[key]) - Number(root.region[key])) > 0.00001;
            }))
            regionEdited(draft);
        draft = null;
    }
    function move(dx, dy) {
        preview(Qt.rect(Math.max(0, Math.min(canvas.width - startRect.width, startRect.x + dx)),
            Math.max(0, Math.min(canvas.height - startRect.height, startRect.y + dy)),
            startRect.width, startRect.height));
    }

    Item {
        id: canvas
        x: root.videoRect.x + root.videoRect.width * root.sourceFramePercent.x / 100
        y: root.videoRect.y + root.videoRect.height * root.sourceFramePercent.y / 100
        width: root.videoRect.width * root.sourceFramePercent.width / 100
        height: root.videoRect.height * root.sourceFramePercent.height / 100

        Rectangle {
            id: box
            x: Number(root.currentRegion.x_percent || 0) * canvas.width / 100
            y: Number(root.currentRegion.y_percent || 0) * canvas.height / 100
            width: Number(root.currentRegion.width_percent || 0) * canvas.width / 100
            height: Number(root.currentRegion.height_percent || 0) * canvas.height / 100
            color: "transparent"
            border.width: root.editing ? 2 : 0
            border.color: Theme.focus
            activeFocusOnTab: true
            Accessible.role: Accessible.Slider
            Accessible.name: qsTr("Vùng che phụ đề gốc")
            Keys.onPressed: function(event) {
                const step = event.modifiers & Qt.ShiftModifier ? 10 : 2;
                let dx = 0;
                let dy = 0;
                if (event.key === Qt.Key_Left) dx = -step;
                else if (event.key === Qt.Key_Right) dx = step;
                else if (event.key === Qt.Key_Up) dy = -step;
                else if (event.key === Qt.Key_Down) dy = step;
                else return;
                root.editingStarted();
                root.startRect = Qt.rect(x, y, width, height);
                root.move(dx, dy);
                root.finishEdit(Qt.rect(x, y, width, height));
                event.accepted = true;
            }
            MouseArea {
                anchors.fill: parent
                preventStealing: true
                cursorShape: Qt.SizeAllCursor
                onPressed: function(mouse) {
                    box.forceActiveFocus();
                    root.startRect = Qt.rect(box.x, box.y, box.width, box.height);
                    root.startPointer = mapToItem(canvas, mouse.x, mouse.y);
                    root.editingStarted();
                }
                onPositionChanged: function(mouse) {
                    if (!pressed) return;
                    const point = mapToItem(canvas, mouse.x, mouse.y);
                    root.move(point.x - root.startPointer.x, point.y - root.startPointer.y);
                }
                onReleased: root.finishEdit(Qt.rect(box.x, box.y, box.width, box.height))
                onCanceled: root.draft = null
            }
            Repeater {
                model: [{h: -1, v: -1}, {h: 1, v: -1}, {h: -1, v: 1}, {h: 1, v: 1}]
                delegate: SubtitleBoxHandle {
                    required property var modelData
                    visible: root.editing
                    selectionItem: box
                    canvasItem: canvas
                    horizontalDirection: modelData.h
                    verticalDirection: modelData.v
                    minimumWidthPixels: Math.min(12, canvas.width)
                    minimumHeightPixels: Math.min(8, canvas.height)
                    Accessible.name: qsTr("Đổi kích thước vùng che phụ đề gốc")
                    onResizeStarted: root.editingStarted()
                    onRectanglePreviewed: function(rectangle) { root.preview(rectangle); }
                    onRectangleCommitted: function(rectangle) { root.finishEdit(rectangle); }
                    onResizeCanceled: root.draft = null
                }
            }
        }
    }
}
