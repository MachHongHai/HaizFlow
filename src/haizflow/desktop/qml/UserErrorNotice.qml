pragma ComponentBehavior: Bound
import QtQuick
import "."

// Error source adapter. The shared host owns the top-right notification stack.
Item {
    id: root
    property string title: qsTr("Thao tác chưa hoàn tất")
    property string details: ""
    property string logText: ""
    property string message: ""
    property var notificationHandler: null
    property bool initialized: false
    property string lastPresented: ""
    property string occurrenceKey: ""
    onOccurrenceKeyChanged: if (initialized) Qt.callLater(root.present)
    readonly property bool scopeVisible: parent !== null && parent.visible
    implicitWidth: 0
    implicitHeight: 0
    visible: false
    Component.onCompleted: { initialized = true; Qt.callLater(root.present); }
    onDetailsChanged: {
        if (!details) lastPresented = "";
        if (initialized) Qt.callLater(root.present);
    }
    onScopeVisibleChanged: if (scopeVisible && initialized) Qt.callLater(root.present)
    function present() {
        const fingerprint = occurrenceKey + "\n" + details;
        if (!scopeVisible || !details || fingerprint === lastPresented) return;
        lastPresented = fingerprint;
        if (notificationHandler) notificationHandler(title, details, logText);
        else AppController.presentUserError(title, details, logText);
    }
}
