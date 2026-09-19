pragma ComponentBehavior: Bound

import QtQuick
import "."

Item {
    id: root

    required property Item selectionItem
    required property Item coordinateItem
    required property int horizontalDirection
    required property int verticalDirection
    property real currentValue: 100
    property real minimumValue: 10
    property real maximumValue: 300
    property string objectNamePrefix: "scaleHandle"
    readonly property bool pressed: resizeArea.pressed

    signal resizeStarted(real value)
    signal valuePreviewed(real value)
    signal valueCommitted(real beforeValue, real afterValue)

    property real startValue: 100
    property real previewValue: 100
    property real pixelsPerUnit: 1
    property real startPointerX: 0
    property real startPointerY: 0

    objectName: objectNamePrefix + "_" + horizontalDirection + "_" + verticalDirection
    z: 4
    x: horizontalDirection < 0 ? -width / 2 : selectionItem.width - width / 2
    y: verticalDirection < 0 ? -height / 2 : selectionItem.height - height / 2
    width: 24
    height: 24

    Rectangle {
        anchors.centerIn: parent
        width: 10
        height: 10
        radius: 2
        color: Theme.focus
        border.width: 2
        border.color: Theme.surface
        Accessible.ignored: true
    }

    MouseArea {
        id: resizeArea
        anchors.fill: parent
        hoverEnabled: true
        preventStealing: true
        cursorShape: root.horizontalDirection === root.verticalDirection
            ? Qt.SizeFDiagCursor : Qt.SizeBDiagCursor

        onPressed: function(mouse) {
            const pointer = mapToItem(root.coordinateItem, mouse.x, mouse.y);
            root.startPointerX = pointer.x;
            root.startPointerY = pointer.y;
            root.startValue = root.currentValue;
            root.previewValue = root.currentValue;
            root.pixelsPerUnit = Math.max(
                0.1,
                Math.max(root.selectionItem.width, root.selectionItem.height)
                    / Math.max(1, root.currentValue)
            );
            root.resizeStarted(root.startValue);
        }
        onPositionChanged: function(mouse) {
            if (!pressed)
                return;
            const pointer = mapToItem(root.coordinateItem, mouse.x, mouse.y);
            const outwardPixels = (
                root.horizontalDirection * (pointer.x - root.startPointerX)
                + root.verticalDirection * (pointer.y - root.startPointerY)
            ) / 2;
            root.previewValue = Math.max(
                root.minimumValue,
                Math.min(
                    root.maximumValue,
                    root.startValue + outwardPixels / root.pixelsPerUnit
                )
            );
            root.valuePreviewed(root.previewValue);
        }
        onReleased: root.valueCommitted(root.startValue, root.previewValue)
        onCanceled: root.valuePreviewed(root.startValue)
    }
}
