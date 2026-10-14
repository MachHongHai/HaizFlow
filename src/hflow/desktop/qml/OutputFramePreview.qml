pragma ComponentBehavior: Bound
import QtQuick
import QtMultimedia

Item {
    id: root
    property string outputFormat: "keep_ratio"
    property url thumbnailSource: ""
    property bool showThumbnail: false
    property string thumbnailOutputFormat: outputFormat
    readonly property bool thumbnailVisible: showThumbnail && thumbnail.status === Image.Ready
    readonly property string displayFormat: thumbnailVisible ? thumbnailOutputFormat : outputFormat
    readonly property Item frameSource: thumbnailVisible ? thumbnail : video
    readonly property rect frameRect: thumbnailVisible
        ? Qt.rect((thumbnail.width - thumbnail.paintedWidth) / 2,
            (thumbnail.height - thumbnail.paintedHeight) / 2, thumbnail.paintedWidth, thumbnail.paintedHeight)
        : video.contentRect
    property alias videoOutput: video
    property alias videoSink: video.videoSink
    property alias endOfStreamPolicy: video.endOfStreamPolicy
    readonly property bool portrait: displayFormat === "blur_background_9_16"
        || displayFormat === "tiktok_9_16_crop"
    readonly property rect contentRect: portrait
        ? Qt.rect(canvas.x, canvas.y, canvas.width, canvas.height) : frameRect
    function clearOutput() { video.clearOutput(); }

    Item {
        id: canvas
        width: root.portrait ? Math.min(root.width, root.height * 9 / 16) : root.width
        height: root.portrait ? width * 16 / 9 : root.height
        anchors.centerIn: parent
        clip: root.portrait

        Loader {
            objectName: "outputBackgroundLoader"
            anchors.fill: parent
            // This shell only captures a tiny frame. Native blur construction
            // remains guarded/asynchronous inside OutputFrameBackground.
            asynchronous: false
            active: root.visible && root.displayFormat === "blur_background_9_16"
                && root.frameRect.width > 0 && root.frameRect.height > 0
            sourceComponent: Component {
                OutputFrameBackground {
                    sourceItem: root.frameSource
                    sourceRect: root.frameRect
                    videoSink: video.videoSink
                }
            }
        }
        VideoOutput {
            id: video
            objectName: "outputFrameVideo"
            anchors.fill: parent
            endOfStreamPolicy: VideoOutput.KeepLastFrame
            fillMode: root.outputFormat === "tiktok_9_16_crop"
                ? VideoOutput.PreserveAspectCrop : VideoOutput.PreserveAspectFit
        }
        Image {
            id: thumbnail
            objectName: "outputFrameThumbnail"
            anchors.fill: parent
            source: root.showThumbnail ? root.thumbnailSource : ""
            sourceSize.width: 960
            sourceSize.height: 540
            fillMode: root.thumbnailOutputFormat === "tiktok_9_16_crop"
                ? Image.PreserveAspectCrop : Image.PreserveAspectFit
            asynchronous: true
            visible: root.thumbnailVisible
        }
    }
}
