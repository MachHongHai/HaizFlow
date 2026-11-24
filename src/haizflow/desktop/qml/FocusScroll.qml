pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import "."

Flickable {
    id: root
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    flickableDirection: Flickable.VerticalFlick
    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

    function revealFocus() {
        const window = root.Window.window;
        const item = window ? window.activeFocusItem : null;
        if (!root.visible || !item || root.contentHeight <= root.height)
            return;
        let owner = item.parent;
        while (owner && owner !== root.contentItem)
            owner = owner.parent;
        if (!owner)
            return;
        const top = item.mapToItem(root.contentItem, 0, 0).y;
        const bottom = top + item.height;
        if (top < root.contentY)
            root.contentY = Math.max(0, top - Theme.space4);
        else if (bottom > root.contentY + root.height)
            root.contentY = Math.min(root.contentHeight - root.height, bottom - root.height + Theme.space4);
    }

    Connections {
        target: root.visible ? root.Window.window : null
        function onActiveFocusItemChanged() { Qt.callLater(root.revealFocus); }
    }
}
