pragma ComponentBehavior: Bound

import QtQuick
import QtMultimedia
import "."

Item {
    id: root

    property rect videoRect: Qt.rect(0, 0, 0, 0)
    property var overlays: []
    property var selectedClipIds: []
    property real timeSeconds: 0
    property bool playing: false
    property bool interactive: true
    // Only the currently visible result surface may own video decoders.  The
    // compare view and fullscreen view both instantiate this component, so
    // using visibility alone would leave duplicate MediaPlayer instances
    // alive underneath a popup.
    property bool mediaActive: true

    signal clipSelected(string clipId)

    Item {
        id: canvas
        x: root.videoRect.x
        y: root.videoRect.y
        width: root.videoRect.width
        height: root.videoRect.height

        Repeater {
            model: root.overlays.filter(function(clip) {
                return String(clip.clip_id || "") !== "watermark-1";
            })

            delegate: Item {
                id: overlay
                required property var modelData
                readonly property string clipId: String(modelData.clip_id || "")
                readonly property var transformData: modelData.transform || ({})
                readonly property bool selected: root.selectedClipIds.indexOf(clipId) >= 0
                readonly property Item loadedItem: contentLoader.item as Item
                readonly property real cropLeft: Math.max(0, Math.min(95,
                    Number(transformData.crop_left_percent || 0)))
                readonly property real cropRight: Math.max(0, Math.min(95 - cropLeft,
                    Number(transformData.crop_right_percent || 0)))
                readonly property real cropTop: Math.max(0, Math.min(95,
                    Number(transformData.crop_top_percent || 0)))
                readonly property real cropBottom: Math.max(0, Math.min(95 - cropTop,
                    Number(transformData.crop_bottom_percent || 0)))
                readonly property real cropWidthRatio: Math.max(0.05,
                    (100 - cropLeft - cropRight) / 100)
                readonly property real cropHeightRatio: Math.max(0.05,
                    (100 - cropTop - cropBottom) / 100)
                width: Math.max(28, loadedItem ? loadedItem.implicitWidth : 120)
                height: Math.max(24, loadedItem ? loadedItem.implicitHeight : 68)
                x: canvas.width * Number(transformData.position_x_percent || 50) / 100 - width / 2
                y: canvas.height * Number(transformData.position_y_percent || 50) / 100 - height / 2
                rotation: Number(transformData.rotation_degrees || 0)
                opacity: Math.max(0, Math.min(1, Number(
                    transformData.opacity_percent === undefined
                        ? 100 : transformData.opacity_percent) / 100))
                transformOrigin: Item.Center
                transform: Scale {
                    origin.x: overlay.width / 2
                    origin.y: overlay.height / 2
                    xScale: Math.max(0.01,
                        Number(overlay.transformData.scale_x_percent || 100) / 100)
                    yScale: Math.max(0.01,
                        Number(overlay.transformData.scale_y_percent || 100) / 100)
                }

                Loader {
                    id: contentLoader
                    anchors.centerIn: parent
                    sourceComponent: String(overlay.modelData.kind || "") === "text"
                        ? textComponent : String(overlay.modelData.kind || "") === "image"
                            ? imageComponent : videoComponent
                }

                Component {
                    id: textComponent
                    Item {
                        id: textOverlay
                        readonly property var styleData: overlay.modelData.style || ({})
                        readonly property var spriteData: overlay.modelData.sprite || ({})
                        readonly property bool hasSprite: String(spriteData.sourceUrl || "").length > 0
                        readonly property real referenceScale: canvas.height / Math.max(1,
                            Number(overlay.modelData.referenceHeight || 1080))
                        readonly property real displayFontSize: Math.max(6,
                            Number(styleData.font_size || 60)
                            * referenceScale)
                        readonly property real padding: Math.max(0,
                            Number(styleData.background_padding || 0)
                            * referenceScale)
                        implicitWidth: hasSprite
                            ? Math.max(1, Number(spriteData.width || 1) * referenceScale)
                            : Math.max(80, canvas.width
                                * Number(styleData.max_width_percent || 72) / 100)
                        implicitHeight: hasSprite
                            ? Math.max(1, Number(spriteData.height || 1) * referenceScale)
                            : overlayText.contentHeight + 2 * padding
                        width: implicitWidth
                        height: implicitHeight

                        Image {
                            anchors.fill: parent
                            visible: textOverlay.hasSprite
                            source: textOverlay.spriteData.sourceUrl || ""
                            sourceSize: Qt.size(
                                Number(textOverlay.spriteData.width || 1),
                                Number(textOverlay.spriteData.height || 1))
                            fillMode: Image.Stretch
                            asynchronous: true
                            mipmap: true
                        }

                        Rectangle {
                            anchors.fill: parent
                            visible: !textOverlay.hasSprite
                                && Number(textOverlay.styleData.background_opacity_percent || 0) > 0
                            color: String(textOverlay.styleData.background_color || "#000000")
                            opacity: Number(textOverlay.styleData.background_opacity_percent || 0) / 100
                            radius: Number(textOverlay.styleData.background_radius || 0)
                                * canvas.height / Math.max(1,
                                    Number(overlay.modelData.referenceHeight || 1080))
                        }

                        Text {
                            id: overlayText
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.leftMargin: textOverlay.padding
                            anchors.rightMargin: textOverlay.padding
                            text: String(overlay.modelData.name || "")
                            visible: !textOverlay.hasSprite
                            color: String(textOverlay.styleData.text_color || "#FFFFFF")
                            font.family: String(textOverlay.styleData.font_family || "Bangers")
                            font.pixelSize: textOverlay.displayFontSize
                            font.weight: Number(textOverlay.styleData.font_weight || 400)
                            font.italic: Boolean(textOverlay.styleData.italic)
                            font.capitalization: Boolean(textOverlay.styleData.uppercase)
                                ? Font.AllUppercase : Font.MixedCase
                            font.letterSpacing: Number(textOverlay.styleData.letter_spacing || 0)
                                * canvas.height / Math.max(1,
                                    Number(overlay.modelData.referenceHeight || 1080))
                            lineHeightMode: Text.ProportionalHeight
                            lineHeight: Number(textOverlay.styleData.line_spacing || 1)
                            horizontalAlignment: String(textOverlay.styleData.alignment || "center") === "left"
                                ? Text.AlignLeft
                                : String(textOverlay.styleData.alignment || "center") === "right"
                                    ? Text.AlignRight : Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            wrapMode: Text.Wrap
                            maximumLineCount: Number(textOverlay.styleData.max_lines || 20)
                            elide: Text.ElideNone
                            style: Number(textOverlay.styleData.outline_width || 0) > 0
                                ? Text.Outline : Text.Normal
                            styleColor: String(textOverlay.styleData.outline_color || "#000000")
                            textFormat: Text.PlainText
                        }
                    }
                }

                Component {
                    id: imageComponent
                    Item {
                        id: imageOverlay
                        implicitWidth: Math.max(80, canvas.width * 0.2)
                        implicitHeight: implicitWidth * (overlayImage.sourceSize.height > 0
                            ? overlayImage.sourceSize.height
                                / Math.max(1, overlayImage.sourceSize.width)
                                * overlay.cropHeightRatio / overlay.cropWidthRatio
                            : overlay.cropHeightRatio / overlay.cropWidthRatio)
                        width: implicitWidth
                        height: implicitHeight

                        Image {
                            id: overlayImage
                            anchors.fill: parent
                            source: overlay.modelData.asset
                                ? overlay.modelData.asset.sourceUrl : ""
                            fillMode: Image.PreserveAspectFit
                            sourceClipRect: sourceSize.width > 0 && sourceSize.height > 0
                                ? Qt.rect(
                                    sourceSize.width * overlay.cropLeft / 100,
                                    sourceSize.height * overlay.cropTop / 100,
                                    sourceSize.width * overlay.cropWidthRatio,
                                    sourceSize.height * overlay.cropHeightRatio)
                                : Qt.rect(0, 0, 0, 0)
                            asynchronous: true
                            mipmap: true
                        }
                    }
                }

                Component {
                    id: videoComponent
                    Item {
                        id: videoOverlay
                        readonly property var assetData: overlay.modelData.asset || ({})
                        readonly property real sourceAspect: Number(assetData.width || 0) > 0
                            && Number(assetData.height || 0) > 0
                            ? Number(assetData.height) / Number(assetData.width) : 9 / 16
                        implicitWidth: Math.max(120, canvas.width * 0.28)
                        implicitHeight: implicitWidth * sourceAspect
                            * overlay.cropHeightRatio / overlay.cropWidthRatio
                        width: implicitWidth
                        height: implicitHeight
                        clip: true

                        readonly property int sourceInMs: Number(
                            overlay.modelData.source_in_ms || 0)
                        readonly property int sourceOutMs: Number(
                            overlay.modelData.source_out_ms || 0)
                        readonly property int sourceDurationMs: Math.max(0,
                            sourceOutMs - sourceInMs)

                        function desiredPositionMs() {
                            let localMs = Math.max(0,
                                root.timeSeconds * 1000
                                - Number(overlay.modelData.start_ms || 0));
                            if (Boolean(overlay.modelData.loop)
                                    && sourceDurationMs > 0)
                                localMs %= sourceDurationMs;
                            else if (sourceDurationMs > 0)
                                localMs = Math.min(localMs, sourceDurationMs);
                            return sourceInMs + localMs;
                        }

                        function synchronize(force) {
                            if (!root.mediaActive || !overlayVideoPlayer.seekable)
                                return;
                            const desired = desiredPositionMs();
                            if (force || Math.abs(overlayVideoPlayer.position - desired) > 140)
                                overlayVideoPlayer.position = desired;
                        }

                        VideoOutput {
                            id: overlayVideoOutput
                            x: -videoOverlay.width * overlay.cropLeft
                                / 100 / overlay.cropWidthRatio
                            y: -videoOverlay.height * overlay.cropTop
                                / 100 / overlay.cropHeightRatio
                            width: videoOverlay.width / overlay.cropWidthRatio
                            height: videoOverlay.height / overlay.cropHeightRatio
                            fillMode: VideoOutput.PreserveAspectFit
                        }
                        MediaPlayer {
                            id: overlayVideoPlayer
                            source: root.mediaActive && overlay.modelData.asset
                                ? overlay.modelData.asset.sourceUrl : ""
                            videoOutput: overlayVideoOutput
                            audioOutput: null
                            loops: overlay.modelData.loop ? MediaPlayer.Infinite : 1
                            onMediaStatusChanged: {
                                if (mediaStatus === MediaPlayer.LoadedMedia
                                        || mediaStatus === MediaPlayer.BufferedMedia) {
                                    videoOverlay.synchronize(true);
                                    if (root.playing)
                                        play();
                                }
                            }
                        }
                        Connections {
                            target: root
                            function onPlayingChanged() {
                                if (!root.mediaActive) {
                                    overlayVideoPlayer.stop();
                                } else if (root.playing) {
                                    videoOverlay.synchronize(true);
                                    overlayVideoPlayer.play();
                                } else {
                                    overlayVideoPlayer.pause();
                                    videoOverlay.synchronize(true);
                                }
                            }
                            function onTimeSecondsChanged() {
                                videoOverlay.synchronize(!root.playing);
                            }
                            function onMediaActiveChanged() {
                                if (!root.mediaActive)
                                    overlayVideoPlayer.stop();
                                else
                                    videoOverlay.synchronize(true);
                            }
                        }
                        Component.onDestruction: overlayVideoPlayer.stop()
                    }
                }

                Rectangle {
                    anchors.fill: parent
                    anchors.margins: -5
                    color: "transparent"
                    border.width: overlay.selected ? 1 : 0
                    border.color: Theme.focus
                    radius: Theme.radiusTiny
                }

                MouseArea {
                    anchors.fill: parent
                    anchors.margins: -8
                    enabled: root.interactive
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    preventStealing: true
                    onPressed: function(mouse) {
                        root.clipSelected(overlay.clipId);
                    }
                }
            }
        }
    }
}
