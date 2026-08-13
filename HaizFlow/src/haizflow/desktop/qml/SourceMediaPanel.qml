import QtQuick
import QtQuick.Layouts
import "."

Panel {
    id: root

    signal requestUrlImport()
    signal requestDownloadProjectImport()

    property bool dropActive: false

    title: I18n.t("Source media")
    subtitle: I18n.t("Input video")
    tone: "blue"

    Rectangle {
        id: videoFrame

        Layout.fillWidth: true
        Layout.preferredHeight: Math.max(230, Math.min(300, width * 9 / 16))
        radius: Theme.radius
        color: root.dropActive ? Theme.interactiveMuted : Theme.video
        border.width: root.dropActive || AppController.videoPath.length > 0 ? 2 : 1
        border.color: root.dropActive ? Theme.focus
            : AppController.videoPath.length > 0 ? Theme.outlineStrong
            : Theme.outline
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
                width: 46
                height: 46
                radius: 23
                color: root.dropActive ? Theme.interactive : Theme.surfaceElevated
                border.width: root.dropActive ? 0 : 1
                border.color: Theme.outlineStrong

                AppIcon {
                    anchors.centerIn: parent
                    width: 22
                    height: 22
                    glyph: root.dropActive ? "\uE898" : "\uE710"
                    iconColor: root.dropActive ? Theme.textOnAccent : Theme.interactive
                    iconSize: Theme.iconLarge
                }
            }

            Text {
                width: parent.width
                text: root.dropActive ? I18n.t("Drop video to import") : I18n.t("Select a source video")
                color: Theme.text
                font.pixelSize: Theme.bodyLarge
                font.weight: Font.DemiBold
                horizontalAlignment: Text.AlignHCenter
                textFormat: Text.PlainText
            }

            Text {
                width: parent.width
                text: root.dropActive ? I18n.t("Release to add the source file") : qsTr("MP4, MOV or MKV")
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

            onEntered: function(drag) {
                if (drag.hasUrls) {
                    root.dropActive = true
                    drag.accept()
                }
            }
            onExited: root.dropActive = false
            onDropped: function(drop) {
                root.dropActive = false
                if (!drop.urls || drop.urls.length === 0)
                    return
                if (AppController.hasSelectedVideo)
                    AppController.replaceSelectedVideoVideo(String(drop.urls[0]))
                else
                    AppController.importVideo(String(drop.urls[0]))
            }
        }

        HoverHandler {
            cursorShape: AppController.videoPath.length === 0 ? Qt.PointingHandCursor : Qt.ArrowCursor
        }

        TapHandler {
            enabled: AppController.videoPath.length === 0 && AppController.canEditSelectedVideo
            onTapped: sourceImportButton.openMenu()
        }

        Behavior on color {
            ColorAnimation { duration: Theme.motionFast }
        }
        Behavior on border.color {
            ColorAnimation { duration: Theme.motionFast }
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
                text: AppController.videoPath.length > 0 ? I18n.t("Source imported") : I18n.t("No source selected")
                color: Theme.text
                font.pixelSize: Theme.caption
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
            }

            Text {
                Layout.fillWidth: true
                text: AppController.videoPath || I18n.t("Choose a file to begin")
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
            text: I18n.t("Replace")
            iconGlyph: "\uE8B7"
            enabled: AppController.canEditSelectedVideo
            onFileRequested: AppController.browseVideo()
            onLinkRequested: root.requestUrlImport()
            onDownloadProjectRequested: root.requestDownloadProjectImport()
        }
    }

}
