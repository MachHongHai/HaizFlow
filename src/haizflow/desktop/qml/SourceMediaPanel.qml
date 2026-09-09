import QtQuick
import QtQuick.Layouts
import "."

AppSurface {
    id: root

    signal requestUrlImport
    signal requestDownloadProjectImport

    property bool dropActive: false
    property bool compact: false

    padding: Theme.space12
    spacing: Theme.space12

    SectionHeader {
        Layout.fillWidth: true
        title: qsTr("Video nguồn")
    }

    Rectangle {
        id: videoFrame

        Layout.fillWidth: true
        Layout.preferredHeight: root.compact ? Math.max(124, Math.min(168, width * 9 / 16)) : Math.max(230, Math.min(300, width * 9 / 16))
        radius: Theme.radius
        color: root.dropActive ? Theme.interactiveMuted : Theme.video
        border.width: root.dropActive || AppController.videoPath.length > 0 ? 2 : 1
        border.color: root.dropActive ? Theme.focus : AppController.videoPath.length > 0 ? Theme.outlineStrong : Theme.outline
        clip: true

        Image {
            id: sourceThumbnail
            anchors.fill: parent
            anchors.margins: 2
            source: AppController.videoThumbnailSource
            sourceSize.width: 960
            sourceSize.height: 540
            fillMode: Image.PreserveAspectFit
            asynchronous: true
            visible: status === Image.Ready
        }

        Column {
            anchors.centerIn: parent
            width: Math.min(330, parent.width - 40)
            spacing: Theme.space8
            visible: AppController.videoThumbnailSource.length === 0 || sourceThumbnail.status === Image.Error

            Rectangle {
                anchors.horizontalCenter: parent.horizontalCenter
                width: root.compact ? 38 : 46
                height: width
                radius: width / 2
                color: root.dropActive ? Theme.interactive : Theme.surfaceElevated
                border.width: root.dropActive ? 0 : 1
                border.color: Theme.outlineStrong

                AppIcon {
                    anchors.centerIn: parent
                    width: root.compact ? 18 : 22
                    height: width
                    glyph: root.dropActive ? "\uE898" : "\uE710"
                    iconColor: root.dropActive ? Theme.textOnAccent : Theme.interactive
                    iconSize: Theme.iconLarge
                }
            }

            Text {
                width: parent.width
                text: root.dropActive ? qsTr("Thả video để nhập") : qsTr("Chọn video nguồn")
                color: Theme.text
                font.pixelSize: Theme.bodyLarge
                font.weight: Font.DemiBold
                horizontalAlignment: Text.AlignHCenter
                textFormat: Text.PlainText
            }

            Text {
                width: parent.width
                text: root.dropActive ? qsTr("Thả để thêm video nguồn") : qsTr("MP4, MOV or MKV")
                color: Theme.textMuted
                font.pixelSize: Theme.caption
                horizontalAlignment: Text.AlignHCenter
                textFormat: Text.PlainText
            }
        }

        DropArea {
            id: sourceDropArea
            anchors.fill: parent
            keys: ["text/uri-list"]
            enabled: AppController.canEditSelectedVideo

            onEntered: function (drag) {
                if (drag.hasUrls) {
                    root.dropActive = true;
                    drag.accept();
                }
            }
            onExited: root.dropActive = false
            onDropped: function (drop) {
                root.dropActive = false;
                if (!drop.urls || drop.urls.length === 0)
                    return;
                if (AppController.hasSelectedVideo)
                    AppController.replaceSelectedVideoVideo(String(drop.urls[0]));
                else
                    AppController.importVideo(String(drop.urls[0]));
            }
        }

        HoverHandler {
            cursorShape: AppController.videoPath.length === 0 ? Qt.PointingHandCursor : Qt.ArrowCursor
        }

        TapHandler {
            enabled: AppController.videoPath.length === 0 && AppController.canEditSelectedVideo
            onTapped: sourceImportButton.openMenu()
        }
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space12

        AppIcon {
            Layout.preferredWidth: 22
            Layout.preferredHeight: 22
            glyph: AppController.videoPath.length > 0 ? "\uE73E" : "\uE7BA"
            iconColor: AppController.videoPath.length > 0 ? Theme.success : Theme.textSubtle
            iconSize: Theme.iconSmall
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            spacing: 2

            Text {
                Layout.fillWidth: true
                text: AppController.videoPath.length > 0 ? qsTr("Đã nhập video nguồn") : qsTr("Chưa chọn video nguồn")
                color: Theme.text
                font.pixelSize: Theme.caption
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
            }

            Text {
                Layout.fillWidth: true
                text: AppController.videoPath || qsTr("Chọn một tệp để bắt đầu")
                color: Theme.textMuted
                font.pixelSize: Theme.caption
                textFormat: Text.PlainText
                elide: Text.ElideMiddle
            }
        }

        MediaSourceImportButton {
            id: sourceImportButton

            visible: AppController.videoPath.length === 0
            Layout.preferredWidth: 132
            enabled: AppController.canEditSelectedVideo
            onFileRequested: AppController.browseVideo()
            onLinkRequested: root.requestUrlImport()
            onDownloadProjectRequested: root.requestDownloadProjectImport()
        }

        MediaSourceImportButton {
            visible: AppController.videoPath.length > 0
            text: qsTr("Thay thế")
            iconGlyph: "\uE8B7"
            enabled: AppController.canEditSelectedVideo
            onFileRequested: AppController.browseVideo()
            onLinkRequested: root.requestUrlImport()
            onDownloadProjectRequested: root.requestDownloadProjectImport()
        }
    }
}
