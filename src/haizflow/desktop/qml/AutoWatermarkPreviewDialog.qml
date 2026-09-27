pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

FloatingToolDialog {
    id: root

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
                source: AppController.videoThumbnailSource
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
                watermarkKind: AppController.watermarkKind
                watermarkText: AppController.watermarkText
                watermarkImageSource: AppController.watermarkImageSource
                watermarkVideoSource: AppController.watermarkVideoSource
                fontFamily: AppController.watermarkFontFamily
                textColor: AppController.watermarkTextColor
                fontBold: AppController.watermarkBold
                fontItalic: AppController.watermarkItalic
                opacityPercent: AppController.watermarkOpacityPercent
                outlinePercent: AppController.watermarkOutlinePercent
                scalePercent: AppController.watermarkScalePercent
                interactive: true
                editing: true
                onScalePreviewChanged: function(value) {
                    AppController.watermarkScalePercent = value;
                }
                onScaleCommitted: function(_before, value) {
                    AppController.watermarkScalePercent = value;
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
                    visible: AppController.watermarkKind === "text"
                    enabled: AppController.canEditSelectedVideo
                    maximumLength: 80
                    placeholderText: qsTr("Nội dung watermark")
                    text: AppController.watermarkText
                    onEditingFinished: {
                        AppController.watermarkText = text;
                        root.watermarkSettingsEdited();
                    }
                }

                StudioButton {
                    Layout.fillWidth: true
                    visible: AppController.watermarkKind === "image"
                    enabled: AppController.canEditSelectedVideo
                    variant: "secondary"
                    text: AppController.watermarkImagePath.length > 0
                        ? qsTr("Đổi ảnh") : qsTr("Chọn ảnh")
                    onClicked: {
                        const path = AppController.chooseWatermarkImage();
                        if (path.length > 0 && AppController.setWatermarkImage(path))
                            root.watermarkSettingsEdited();
                    }
                }

                StudioButton {
                    Layout.fillWidth: true
                    visible: AppController.watermarkKind === "video"
                    enabled: AppController.canEditSelectedVideo
                    variant: "secondary"
                    text: AppController.watermarkVideoPath.length > 0
                        ? qsTr("Đổi video") : qsTr("Chọn video")
                    onClicked: {
                        const path = AppController.chooseWatermarkVideo();
                        if (path.length > 0 && AppController.setWatermarkVideo(path))
                            root.watermarkSettingsEdited();
                    }
                }

                SettingLabel {
                    Layout.fillWidth: true
                    text: qsTr("Độ hiển thị · %1%")
                        .arg(AppController.watermarkOpacityPercent)
                }
                StudioSlider {
                    Layout.fillWidth: true
                    enabled: AppController.canEditSelectedVideo
                    from: 0
                    to: 100
                    stepSize: 1
                    value: AppController.watermarkOpacityPercent
                    Accessible.name: qsTr("Độ hiển thị watermark")
                    onMoved: AppController.watermarkOpacityPercent = Math.round(value)
                    onPressedChanged: if (!pressed) root.watermarkSettingsEdited()
                }

                ManualWatermarkStyleControls {
                    Layout.fillWidth: true
                    visible: AppController.watermarkKind === "text"
                    enabled: AppController.canEditSelectedVideo
                    onWatermarkStyleEdited: root.watermarkSettingsEdited()
                }
            }

            ScrollBar.vertical: ScrollBar {}
        }
    }
}
