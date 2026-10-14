pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import QtMultimedia
import "."

Rectangle {
    id: root

    property url thumbnailSource: ""
    property bool previewReady: false
    property bool statusVisible: false
    property bool busy: false
    property real progress: 0
    property string statusText: ""
    property real position: 0
    property real duration: 1
    property bool playing: false
    property alias videoOutput: editorVideoOutput

    signal playbackToggled()
    signal scrubStarted(real position)
    signal scrubbed(real position)
    signal scrubFinished(real position)
    signal fullscreenRequested()

    color: Theme.video
    radius: Theme.radiusSmall
    border.width: 1
    border.color: Theme.outline
    clip: true

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 1
        spacing: 0

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true

            Rectangle {
                anchors.fill: parent
                color: Theme.surfaceMuted
                visible: !root.previewReady

                Column {
                    anchors.centerIn: parent
                    spacing: Theme.space8

                    AppIcon {
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: 28
                        height: 28
                        glyph: IconCatalog.glyph("video")
                        iconColor: Theme.textSubtle
                        iconSize: 28
                    }

                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: qsTr("Đang chuẩn bị preview")
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.caption
                        textFormat: Text.PlainText
                    }
                }
            }

            Image {
                anchors.fill: parent
                source: root.thumbnailSource
                sourceSize.width: 1280
                sourceSize.height: 720
                fillMode: Image.PreserveAspectFit
                asynchronous: true
                visible: !root.previewReady && status === Image.Ready
                z: 1
            }

            VideoOutput {
                id: editorVideoOutput
                anchors.fill: parent
                fillMode: VideoOutput.PreserveAspectFit
            }

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: 30
                color: Theme.captionOverlay
                visible: root.statusVisible && root.busy
                z: 4

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: Theme.space12
                    anchors.rightMargin: Theme.space12
                    spacing: Theme.space8

                    Text {
                        Layout.fillWidth: true
                        text: root.statusText
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.caption
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                    }

                    Text {
                        visible: root.progress > 0
                        text: qsTr("%1%").arg(Math.round(root.progress * 100))
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                        font.family: "Cascadia Mono"
                        textFormat: Text.PlainText
                    }
                }

                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    height: 2
                    color: Theme.outline

                    Rectangle {
                        width: parent.width * Math.max(0, Math.min(1, root.progress))
                        height: parent.height
                        color: Theme.interactive
                    }
                }
            }
        }

        PreviewTransport {
            Layout.fillWidth: true
            position: root.position
            duration: root.duration
            playing: root.playing
            onPlaybackToggled: root.playbackToggled()
            onScrubStarted: function(value) { root.scrubStarted(value); }
            onScrubbed: function(value) { root.scrubbed(value); }
            onScrubFinished: function(value) { root.scrubFinished(value); }
            onFullscreenRequested: root.fullscreenRequested()
        }
    }
}
