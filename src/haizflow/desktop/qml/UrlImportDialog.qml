import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

AppDialog {
    id: root
    objectName: "urlImportDialog"

    property string importMode: "single"
    property string inspectedText: ""
    // Python's generated qmltypes omit the constant flag; the importer is stable.
    // qmllint disable stale-property-read
    readonly property var importer: AppController.urlImporter
    // qmllint enable stale-property-read
    readonly property bool hasMetadata: importer.title.length > 0
    readonly property bool hasStatus: importer.status.length > 0
    readonly property bool canDownload: importer.state === "ready" || importer.state === "retry"

    title: qsTr("Nhập từ liên kết")
    subtitle: qsTr("YouTube, TikTok hoặc Douyin")
    preferredWidth: 620
    preferredHeight: hasMetadata ? 460 : hasStatus ? 340 : 270
    maximumWidth: 660
    maximumHeight: 620
    closePolicy: importer.busy ? Popup.NoAutoClose : Popup.CloseOnEscape

    function openForMode(mode) {
        importMode = mode === "batch" ? "batch" : "single"
        importer.begin(importMode)
        open()
    }

    onOpened: {
        videoUrl.clear()
        inspectedText = ""
        videoUrl.forceActiveFocus()
    }

    Connections {
        target: root.importer

        function onChanged() {
            if (root.canDownload && root.inspectedText.length === 0)
                root.inspectedText = videoUrl.text.trim()
        }
    }

    Connections {
        target: AppController

        function onUrlImportFinished() {
            if (root.opened)
                root.close()
        }
    }

    SettingLabel {
        Layout.fillWidth: true
        text: qsTr("Liên kết video")
    }

    StudioField {
        id: videoUrl

        Layout.fillWidth: true
        enabled: !root.importer.busy
        placeholderText: qsTr("Dán liên kết video")
        accessibleName: qsTr("Liên kết video")
        selectByMouse: true

        onTextEdited: {
            if (text.trim() !== root.inspectedText)
                root.inspectedText = ""
        }

        Keys.onReturnPressed: {
            if (!root.importer.busy && text.trim().length > 0) {
                root.inspectedText = ""
                root.importer.inspect(text.trim())
            }
        }
    }

    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: 108
        visible: root.hasMetadata
        radius: Theme.radiusSmall
        color: Theme.surfaceElevated
        border.width: 1
        border.color: Theme.outline

        RowLayout {
            anchors.fill: parent
            anchors.margins: Theme.space8
            spacing: Theme.space12

            MediaThumbnail {
                Layout.preferredWidth: 150
                Layout.fillHeight: true
                source: root.importer.thumbnailSource
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: Theme.space4

                Text {
                    Layout.fillWidth: true
                    text: root.importer.title
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.control
                    font.weight: Font.DemiBold
                    maximumLineCount: 2
                    wrapMode: Text.Wrap
                    elide: Text.ElideRight
                    textFormat: Text.PlainText
                }

                Text {
                    Layout.fillWidth: true
                    visible: root.importer.uploader.length > 0
                    text: root.importer.uploader
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.metadata
                    elide: Text.ElideRight
                    textFormat: Text.PlainText
                }

                Item { Layout.fillHeight: true }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space8

                    StatusBadge {
                        label: root.importer.platform
                        status: "ready"
                    }

                    Text {
                        visible: root.importer.duration.length > 0
                        text: root.importer.duration
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: TypeScale.metadata
                        textFormat: Text.PlainText
                    }
                }
            }
        }
    }

    InlineBanner {
        Layout.fillWidth: true
        visible: root.hasStatus
        tone: root.importer.state === "error" || root.importer.state === "retry" ? "danger"
            : root.importer.state === "ready" ? "success" : "info"
        busy: root.importer.busy
        title: root.importer.state === "ready" ? qsTr("Liên kết hợp lệ")
            : root.importer.state === "retry" ? qsTr("Không tải được video")
            : ""
        message: I18n.runtimeStatus(root.importer.status)
    }

    AppProgressBar {
        Layout.fillWidth: true
        visible: root.importer.state === "downloading" || root.importer.state === "importing"
        value: root.importer.progress
    }

    footerActions: [
        StudioButton {
            text: root.importer.busy ? qsTr("Dừng tải") : qsTr("Hủy")
            variant: root.importer.busy ? "danger" : "secondary"
            onClicked: {
                if (root.importer.busy)
                    root.importer.cancel()
                else
                    root.close()
            }
        },
        StudioButton {
            text: root.canDownload && root.inspectedText.length > 0
                ? (root.importer.state === "retry" ? qsTr("Thử tải lại") : qsTr("Tải và nhập"))
                : qsTr("Kiểm tra")
            iconName: root.canDownload && root.inspectedText.length > 0 ? "download" : "search"
            variant: "primary"
            enabled: !root.importer.busy && videoUrl.text.trim().length > 0
            onClicked: {
                if (root.canDownload && root.inspectedText.length > 0)
                    AppController.downloadInspectedVideo()
                else {
                    root.inspectedText = ""
                    root.importer.inspect(videoUrl.text.trim())
                }
            }
        }
    ]
}
