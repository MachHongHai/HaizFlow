pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

FloatingToolDialog {
    id: root
    property var controller: AppController

    signal watermarkSettingsEdited()

    expandedWidth: 1040
    expandedHeight: 720
    toolTitle: qsTr("Watermark")
    toolSubtitle: qsTr("Kéo góc trên hình để đổi kích thước")

    function openForSelectedVideo() {
        open();
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: Theme.space16
        spacing: Theme.space16

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumWidth: 360
            color: Theme.video
            radius: Theme.radiusSmall
            border.width: 1
            border.color: Theme.outline
            clip: true

            Image {
                id: previewImage
                anchors.fill: parent
                anchors.margins: 1
                source: root.controller.videoThumbnailSource
                sourceSize.width: 1280
                sourceSize.height: 720
                fillMode: Image.PreserveAspectFit
                asynchronous: true
            }

            WatermarkTransformOverlay {
                anchors.fill: parent
                videoRect: Qt.rect(
                    previewImage.x + (previewImage.width - previewImage.paintedWidth) / 2,
                    previewImage.y + (previewImage.height - previewImage.paintedHeight) / 2,
                    previewImage.paintedWidth,
                    previewImage.paintedHeight)
                watermarkKind: root.controller.watermarkKind
                watermarkText: root.controller.watermarkText
                watermarkImageSource: root.controller.watermarkImageSource
                watermarkVideoSource: root.controller.watermarkVideoSource
                fontFamily: root.controller.watermarkFontFamily
                textColor: root.controller.watermarkTextColor
                fontBold: root.controller.watermarkBold
                fontItalic: root.controller.watermarkItalic
                opacityPercent: root.controller.watermarkOpacityPercent
                outlinePercent: root.controller.watermarkOutlinePercent
                scalePercent: root.controller.watermarkScalePercent
                interactive: true
                editing: true
                onScalePreviewChanged: function(value) {
                    root.controller.watermarkScalePercent = value;
                }
                onScaleCommitted: function(_before, value) {
                    root.controller.watermarkScalePercent = value;
                    root.watermarkSettingsEdited();
                }
            }
        }

        Flickable {
            Layout.preferredWidth: 280
            Layout.fillHeight: true
            contentWidth: width
            contentHeight: controls.implicitHeight
            boundsBehavior: Flickable.StopAtBounds
            clip: true

            ColumnLayout {
                id: controls
                width: parent.width
                spacing: Theme.space12

                StudioField {
                    Layout.fillWidth: true
                    visible: root.controller.watermarkKind === "text"
                    enabled: root.controller.canEditSelectedVideo
                    maximumLength: 80
                    placeholderText: qsTr("Nội dung watermark")
                    text: root.controller.watermarkText
                    onEditingFinished: {
                        root.controller.watermarkText = text;
                        root.watermarkSettingsEdited();
                    }
                }

                StudioButton {
                    Layout.fillWidth: true
                    visible: root.controller.watermarkKind === "image"
                    enabled: root.controller.canEditSelectedVideo
                    variant: "secondary"
                    text: root.controller.watermarkImagePath.length > 0
                        ? qsTr("Đổi ảnh") : qsTr("Chọn ảnh")
                    onClicked: {
                        const path = root.controller.chooseWatermarkImage();
                        if (path.length > 0 && root.controller.setWatermarkImage(path))
                            root.watermarkSettingsEdited();
                    }
                }

                StudioButton {
                    Layout.fillWidth: true
                    visible: root.controller.watermarkKind === "video"
                    enabled: root.controller.canEditSelectedVideo
                    variant: "secondary"
                    text: root.controller.watermarkVideoPath.length > 0
                        ? qsTr("Đổi video") : qsTr("Chọn video")
                    onClicked: {
                        const path = root.controller.chooseWatermarkVideo();
                        if (path.length > 0 && root.controller.setWatermarkVideo(path))
                            root.watermarkSettingsEdited();
                    }
                }

                SettingLabel {
                    Layout.fillWidth: true
                    text: qsTr("Độ hiển thị · %1%")
                        .arg(root.controller.watermarkOpacityPercent)
                }
                StudioSlider {
                    Layout.fillWidth: true
                    enabled: root.controller.canEditSelectedVideo
                    from: 0
                    to: 100
                    stepSize: 1
                    value: root.controller.watermarkOpacityPercent
                    Accessible.name: qsTr("Độ hiển thị watermark")
                    onMoved: root.controller.watermarkOpacityPercent = Math.round(value)
                    onPressedChanged: if (!pressed) root.watermarkSettingsEdited()
                }

                ManualWatermarkStyleControls {
                    controller: root.controller
                    Layout.fillWidth: true
                    visible: root.controller.watermarkKind === "text"
                    enabled: root.controller.canEditSelectedVideo
                    onWatermarkStyleEdited: root.watermarkSettingsEdited()
                }
            }

            ScrollBar.vertical: ScrollBar {}
        }
    }
}
