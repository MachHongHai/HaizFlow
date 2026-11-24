pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root
    property SettingsPage generalPage: null
    property var continuation: null
    property bool leaving: false
    property bool canApply: true
    title: qsTr("Thay đổi chưa áp dụng")
    onClosed: {
        const next = root.leaving ? root.continuation : null;
        root.leaving = false;
        root.continuation = null;
        if (next)
            Qt.callLater(next);
    }

    function ask(next) {
        if (!root.visible) {
            root.continuation = next;
            root.open();
        }
    }

    function proceed(apply) {
        if (root.generalPage) {
            if (apply && !root.generalPage.applyDraft())
                return;
            if (!apply)
                root.generalPage.loadDraft();
        }
        root.leaving = true;
        root.close();
    }

    Text {
        Layout.fillWidth: true
        text: root.canApply ? qsTr("Áp dụng thay đổi trước khi rời Cài đặt?")
            : qsTr("Chờ xử lý xong để áp dụng, hoặc bỏ thay đổi để rời Cài đặt.")
        color: Theme.text
        font.pixelSize: TypeScale.body
        wrapMode: Text.WordWrap
    }

    footerActions: [
        StudioButton { objectName: "stayInSettings"; text: qsTr("Ở lại"); variant: "ghost"; onClicked: root.close() },
        StudioButton { objectName: "discardSettingsAndLeave"; text: qsTr("Bỏ thay đổi"); onClicked: root.proceed(false) },
        StudioButton {
            objectName: "applySettingsAndLeave"
            text: qsTr("Áp dụng")
            variant: "primary"
            enabled: root.canApply
            onClicked: root.proceed(true)
        }
    ]
}
