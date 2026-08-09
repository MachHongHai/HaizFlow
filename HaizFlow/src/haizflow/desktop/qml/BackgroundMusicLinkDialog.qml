import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Dialog {
    id: root

    property bool batchMode: false
    signal batchMusicReady(string path)

    modal: true
    focus: true
    title: I18n.t("Import background music from link")
    parent: Overlay.overlay
    width: Math.min(560, parent ? parent.width - 48 : 560)
    padding: Theme.space24
    closePolicy: AppController.backgroundMusicImportBusy
        ? Popup.NoAutoClose
        : Popup.CloseOnEscape | Popup.CloseOnPressOutside
    x: Math.round((parent.width - width) / 2)
    y: Math.round((parent.height - height) / 2)

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

    contentItem: ColumnLayout {
        spacing: Theme.space16

        Text {
            Layout.fillWidth: true
            text: I18n.t("Paste a public video or audio link")
            color: Theme.textMuted
            font.pixelSize: Theme.body
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
        }

        TextField {
            id: musicUrl
            Layout.fillWidth: true
            implicitHeight: 46
            enabled: !AppController.backgroundMusicImportBusy
            placeholderText: I18n.t("Paste a video link")
            selectByMouse: true
            activeFocusOnTab: true
            Accessible.name: I18n.t("Background music link")
            background: Rectangle {
                radius: Theme.radiusSmall
                color: Theme.input
                border.width: musicUrl.activeFocus ? 2 : 1
                border.color: musicUrl.activeFocus ? Theme.focus : Theme.outline
            }
            Keys.onReturnPressed: {
                if (text.trim().length > 0 && !AppController.backgroundMusicImportBusy)
                    root.batchMode
                        ? AppController.importBatchBackgroundMusicFromLink(text.trim())
                        : AppController.importBackgroundMusicFromLink(text.trim())
            }
        }

        RowLayout {
            Layout.fillWidth: true
            visible: AppController.backgroundMusicImportBusy
                || AppController.backgroundMusicImportStatus.length > 0
            spacing: Theme.space8

            BusyIndicator {
                Layout.preferredWidth: 22
                Layout.preferredHeight: 22
                running: AppController.backgroundMusicImportBusy
                visible: running
            }

            Text {
                Layout.fillWidth: true
                text: I18n.t(AppController.backgroundMusicImportStatus)
                color: AppController.backgroundMusicImportBusy ? Theme.textMuted : Theme.danger
                wrapMode: Text.WordWrap
                textFormat: Text.PlainText
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: Theme.space4

            Item { Layout.fillWidth: true }

            AppButton {
                text: AppController.backgroundMusicImportBusy ? I18n.t("Cancel") : I18n.t("Close")
                tone: AppController.backgroundMusicImportBusy ? "danger" : "secondary"
                onClicked: {
                    if (AppController.backgroundMusicImportBusy)
                        AppController.cancelBackgroundMusicLinkImport()
                    else
                        root.close()
                }
            }

            AppButton {
                text: I18n.t("Download background music")
                tone: "primary"
                enabled: musicUrl.text.trim().length > 0 && !AppController.backgroundMusicImportBusy
                onClicked: {
                    if (root.batchMode)
                        AppController.importBatchBackgroundMusicFromLink(musicUrl.text.trim())
                    else
                        AppController.importBackgroundMusicFromLink(musicUrl.text.trim())
                }
            }
        }
    }
}
