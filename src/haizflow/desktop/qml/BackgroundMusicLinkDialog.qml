pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

AppDialog {
    id: root
    objectName: "backgroundMusicLinkDialog"

    property bool batchMode: false
    property var controller: AppController
    property bool submitted: false
    readonly property bool busy: controller.backgroundMusicImportBusy
    readonly property string importStatus: String(controller.backgroundMusicImportStatus || "")
    readonly property bool hasError: submitted && !busy && importStatus.length > 0
        && importStatus !== "Background music imported"
    signal batchMusicReady(string path)

    preferredWidth: 620
    maximumWidth: 660
    title: qsTr("Nhạc nền từ liên kết")
    subtitle: qsTr("YouTube, TikTok hoặc Douyin")
    closePolicy: root.busy
        ? Popup.NoAutoClose : Popup.CloseOnEscape

    function startImport() {
        const url = musicUrl.text.trim()
        if (url.length === 0 || root.busy)
            return
        submitted = true
        if (root.batchMode)
            controller.importBatchBackgroundMusicFromLink(url)
        else
            controller.importBackgroundMusicFromLink(url)
    }

    onOpened: {
        musicUrl.clear()
        submitted = root.busy
        musicUrl.forceActiveFocus()
    }

    Connections {
        target: root.controller

        function onBackgroundMusicImportChanged() {
            if (root.opened && root.submitted && !root.busy
                    && !root.batchMode
                    && root.importStatus === "Background music imported")
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
        objectName: "backgroundMusicLinkField"
        Layout.fillWidth: true
        enabled: !root.busy
        placeholderText: "https://…"
        accessibleName: qsTr("Liên kết nhạc nền")
        selectByMouse: true
        onTextEdited: if (!root.busy) root.submitted = false
        Keys.onReturnPressed: root.startImport()
    }

    RowLayout {
        Layout.fillWidth: true
        visible: root.busy || root.hasError
        spacing: Theme.space8
        Text {
            Layout.fillWidth: true
            text: root.busy ? qsTr("Đang tải âm thanh…")
                : root.importStatus.length > 160 ? qsTr("Không nhập được nhạc nền. Xem chi tiết lỗi.")
                : I18n.runtimeStatus(root.importStatus)
            color: root.hasError ? Theme.danger : Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.metadata
            wrapMode: Text.Wrap
            textFormat: Text.PlainText
        }
        StudioIconButton {
            visible: root.hasError
            iconName: "info"
            toolTipText: qsTr("Chi tiết lỗi")
            onClicked: root.controller.showAppAlert(qsTr("Không nhập được nhạc nền"),
                I18n.runtimeStatus(root.importStatus), "warning")
        }
    }

    AppProgressBar {
        Layout.fillWidth: true
        visible: root.busy
        indeterminate: true
        active: root.busy
    }

    footerActions: [
        StudioButton {
            text: root.busy ? qsTr("Dừng tải") : qsTr("Hủy")
            variant: root.busy ? "danger" : "secondary"
            onClicked: {
                if (root.busy)
                    root.controller.cancelBackgroundMusicLinkImport()
                else
                    root.close()
            }
        },
        StudioButton {
            text: qsTr("Nhập nhạc nền")
            variant: "primary"
            enabled: musicUrl.text.trim().length > 0
                && !root.busy
            onClicked: root.startImport()
        }
    ]
}
