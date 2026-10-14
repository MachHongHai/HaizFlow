import QtQuick
import "."

StudioButton {
    id: root
    property string readyText: ""
    property bool actionEnabled: true
    property var actionContext: ({})
    property var pendingContext: null
    property bool executing: false
    readonly property bool preparing: dispatchTimer.running || executing
    signal execute(var context)

    text: preparing ? qsTr("Đang chuẩn bị…") : readyText
    enabled: actionEnabled && !preparing

    onClicked: {
        if (preparing || !actionEnabled)
            return;
        pendingContext = JSON.parse(JSON.stringify(actionContext));
        dispatchTimer.start();
    }
    onVisibleChanged: {
        if (!visible && !executing) {
            dispatchTimer.stop();
            pendingContext = null;
        }
    }
    Timer {
        id: dispatchTimer
        interval: 32
        repeat: false
        onTriggered: {
            const context = root.pendingContext;
            root.pendingContext = null;
            if (!root.visible || !root.actionEnabled)
                return;
            root.executing = true;
            try {
                root.execute(context);
            } finally {
                root.executing = false;
            }
        }
    }
}
