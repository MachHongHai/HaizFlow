pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

FloatingToolDialog {
    id: root

    signal subtitleLayoutEdited(int fontSize, int positionX, int positionY, int boxWidth, int boxHeight)

    property int draftFontSize: 60
    property int draftPositionX: 51
    property int draftPositionY: 96
    property int draftBoxWidth: 72
    property int draftBoxHeight: 6

    function clamp(value, minimum, maximum) {
        return Math.max(minimum, Math.min(maximum, value));
    }

    function openWithLayout(fontSize, positionX, positionY, boxWidth, boxHeight) {
        draftFontSize = clamp(Number(fontSize), 10, 240);
        draftPositionX = clamp(Number(positionX), 0, 100);
        draftPositionY = clamp(Number(positionY), 0, 100);
        draftBoxWidth = clamp(Number(boxWidth), 20, 100);
        draftBoxHeight = clamp(Number(boxHeight), 1, 100);
        open();
    }

    expandedWidth: 920
    expandedHeight: 700
    toolTitle: qsTr("Xem trước phụ đề")
    toolSubtitle: qsTr("Kéo chữ để di chuyển · Kéo góc để đổi cỡ")

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.space16
        spacing: Theme.space12

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 360
            radius: Theme.radiusSmall
            color: Theme.video
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

            SubtitleTransformOverlay {
                anchors.fill: parent
                videoRect: Qt.rect(
                    previewImage.x + (previewImage.width - previewImage.paintedWidth) / 2,
                    previewImage.y + (previewImage.height - previewImage.paintedHeight) / 2,
                    previewImage.paintedWidth,
                    previewImage.paintedHeight)
                sampleText: qsTr("PHỤ ĐỀ MẪU")
                sampleFontFamily: sampleFont.name
                sampleTextColor: AppController.subtitleTextColor
                sampleOutlineColor: AppController.subtitleOutlineColor
                sampleBold: AppController.subtitleBold
                sampleItalic: AppController.subtitleItalic
                fontSize: root.draftFontSize
                positionXPercent: root.draftPositionX
                positionYPercent: root.draftPositionY
                boxWidthPercent: root.draftBoxWidth
                interactive: true
                editing: true
                onLayoutCommitted: function(fontSize, positionX, positionY) {
                    root.draftFontSize = fontSize;
                    root.draftPositionX = positionX;
                    root.draftPositionY = positionY;
                    root.subtitleLayoutEdited(fontSize, positionX, positionY,
                        root.draftBoxWidth, root.draftBoxHeight);
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            StudioButton {
                text: qsTr("Đặt lại")
                variant: "secondary"
                onClicked: {
                    root.draftPositionX = 51;
                    root.draftPositionY = 96;
                    root.subtitleLayoutEdited(root.draftFontSize, 51, 96,
                        root.draftBoxWidth, root.draftBoxHeight);
                }
            }
            Item { Layout.fillWidth: true }
        }
    }

    FontLoader {
        id: sampleFont
        source: "../../assets/fonts/Bangers-Regular.ttf"
    }
}
