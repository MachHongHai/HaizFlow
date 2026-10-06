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
    readonly property bool inspectedLinkMatches: inspectedText.length > 0 && inspectedText === videoUrl.text.trim()
    readonly property bool hasMetadata: inspectedLinkMatches && importer.title.length > 0
    readonly property bool hasStatus: inspectedLinkMatches && importer.status.length > 0
        && importer.state !== "ready" && importer.state !== "success"
    readonly property bool canDownload: importer.state === "ready" || importer.state === "retry"
    readonly property bool failed: importer.state === "error" || importer.state === "retry"
    readonly property string statusText: importer.state === "inspecting" ? qsTr("Đang lấy thông tin video…")
        : importer.state === "downloading" ? qsTr("Đang tải video…")
        : importer.state === "importing" ? qsTr("Đang nhập video…")
        : importer.state === "cancelling" ? qsTr("Đang dừng tải…")
        : failed && importer.status.indexOf("Douyin did not provide playable video data.") >= 0
            ? I18n.runtimeStatus(importer.status)
        : failed && importer.status.length > 160 ? qsTr("Không nhập được video. Xem chi tiết lỗi.")
        : I18n.runtimeStatus(importer.status)

    title: qsTr("Nhập từ liên kết")
    subtitle: qsTr("YouTube, TikTok hoặc Douyin")
    preferredWidth: 620
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

    function inspectLink() {
        inspectedText = videoUrl.text.trim()
        importer.inspect(inspectedText)
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
                root.inspectLink()
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

                    Text {
                        text: root.importer.platform
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: TypeScale.metadata
                        textFormat: Text.PlainText
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

    RowLayout {
        Layout.fillWidth: true
        visible: root.hasStatus
        spacing: Theme.space8
        Text {
            Layout.fillWidth: true
            text: root.statusText
            color: root.failed ? Theme.danger : Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.metadata
            wrapMode: Text.Wrap
            textFormat: Text.PlainText
        }
        StudioIconButton {
            visible: root.failed
            iconName: "info"
            toolTipText: qsTr("Chi tiết lỗi")
            onClicked: AppController.showAppAlert(qsTr("Không nhập được video"),
                I18n.runtimeStatus(root.importer.status), "warning")
        }
    }

    AppProgressBar {
        Layout.fillWidth: true
        visible: root.importer.state === "downloading" || root.importer.state === "importing"
        value: root.importer.progress
        indeterminate: root.importer.state === "importing" || root.importer.progress <= 0
        active: root.importer.busy
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
            text: root.canDownload && root.inspectedLinkMatches
                ? (root.importer.state === "retry" ? qsTr("Thử tải lại") : qsTr("Tải và nhập"))
                : qsTr("Kiểm tra")
            iconName: root.canDownload && root.inspectedLinkMatches ? "download" : "search"
            variant: "primary"
            enabled: !root.importer.busy && videoUrl.text.trim().length > 0
            onClicked: {
                if (root.canDownload && root.inspectedLinkMatches)
                    AppController.downloadInspectedVideo()
                else {
                    root.inspectLink()
                }
            }
        }
    ]
}
