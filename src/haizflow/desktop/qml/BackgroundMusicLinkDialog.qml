pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

AppDialog {
    id: root

    property bool batchMode: false
    signal batchMusicReady(string path)

    preferredWidth: 520
    maximumWidth: 560
    title: qsTr("Nhập nhạc nền từ liên kết")
    closePolicy: AppController.backgroundMusicImportBusy
        ? Popup.NoAutoClose : Popup.CloseOnEscape

    function startImport() {
        const url = musicUrl.text.trim()
        if (url.length === 0 || AppController.backgroundMusicImportBusy)
            return
        if (root.batchMode)
            AppController.importBatchBackgroundMusicFromLink(url)
        else
            AppController.importBackgroundMusicFromLink(url)
    }

    onOpened: {
        musicUrl.clear()
        musicUrl.forceActiveFocus()
    }

    Connections {
        target: AppController

        function onBackgroundMusicImportChanged() {
            if (root.opened && !AppController.backgroundMusicImportBusy
                    && !root.batchMode
                    && AppController.backgroundMusicImportStatus === "Background music imported")
                root.close()
        }

        function onBatchBackgroundMusicDraftReady(path) {
            if (!root.opened || !root.batchMode)
                return
            root.batchMusicReady(path)
            root.close()
        }
    }

    SettingLabel {
        Layout.fillWidth: true
        text: qsTr("Liên kết nhạc nền")
    }

    StudioField {
        id: musicUrl
        Layout.fillWidth: true
        enabled: !AppController.backgroundMusicImportBusy
        placeholderText: qsTr("Dán liên kết video")
        accessibleName: qsTr("Liên kết nhạc nền")
        selectByMouse: true
        Keys.onReturnPressed: root.startImport()
    }

    InlineBanner {
        Layout.fillWidth: true
        visible: AppController.backgroundMusicImportBusy
            || AppController.backgroundMusicImportStatus.length > 0
        tone: AppController.backgroundMusicImportBusy ? "info" : "danger"
        message: I18n.runtimeStatus(AppController.backgroundMusicImportStatus)
        busy: AppController.backgroundMusicImportBusy
    }

    footerActions: [
        StudioButton {
            text: AppController.backgroundMusicImportBusy
                ? qsTr("Hủy") : qsTr("Đóng")
            variant: AppController.backgroundMusicImportBusy ? "danger" : "ghost"
            onClicked: {
                if (AppController.backgroundMusicImportBusy)
                    AppController.cancelBackgroundMusicLinkImport()
                else
                    root.close()
            }
        },
        StudioButton {
            text: qsTr("Tải nhạc nền")
            variant: "primary"
            enabled: musicUrl.text.trim().length > 0
                && !AppController.backgroundMusicImportBusy
            onClicked: root.startImport()
        }
    ]
}
