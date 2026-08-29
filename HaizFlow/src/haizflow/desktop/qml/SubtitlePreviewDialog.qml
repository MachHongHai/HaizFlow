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
        return Math.max(minimum, Math.min(maximum, value))
    }

    function openWithLayout(fontSize, positionX, positionY, boxWidth, boxHeight) {
        draftFontSize = root.clamp(Number(fontSize), 10, 160)
        draftPositionX = root.clamp(Number(positionX), 0, 100)
        draftPositionY = root.clamp(Number(positionY), 0, 100)
        draftBoxWidth = root.clamp(Number(boxWidth), 20, 100)
        draftBoxHeight = root.clamp(Number(boxHeight), 1, 100)
        open()
        Qt.callLater(syncEditorPosition)
    }

    function syncEditorPosition() {
        if (editorCanvas.width <= 0 || editorCanvas.height <= 0)
            return
        subtitleSample.x = root.clamp(
            editorCanvas.width * draftPositionX / 100 - subtitleSample.width / 2,
            0,
            editorCanvas.width - subtitleSample.width
        )
        subtitleSample.y = root.clamp(
            editorCanvas.height * draftPositionY / 100 - subtitleSample.height / 2,
            0,
            editorCanvas.height - subtitleSample.height
        )
    }

    function commitEditorPosition() {
        if (editorCanvas.width <= 0 || editorCanvas.height <= 0)
            return
        draftPositionX = Math.round(root.clamp((subtitleSample.x + subtitleSample.width / 2) / editorCanvas.width * 100, 0, 100))
        draftPositionY = Math.round(root.clamp((subtitleSample.y + subtitleSample.height / 2) / editorCanvas.height * 100, 0, 100))
        subtitleLayoutEdited(draftFontSize, draftPositionX, draftPositionY, draftBoxWidth, draftBoxHeight)
    }

    expandedWidth: 920
    expandedHeight: 760
    toolTitle: qsTr("Xem trước phụ đề mới")
    toolSubtitle: qsTr("Kéo phụ đề để di chuyển; dùng thanh trượt để đổi cỡ chữ")

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.space16
        spacing: Theme.space16

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

            Item {
                id: editorCanvas

                anchors.centerIn: parent
                width: previewImage.status === Image.Ready ? previewImage.paintedWidth : parent.width
                height: previewImage.status === Image.Ready ? previewImage.paintedHeight : parent.height

                onWidthChanged: if (root.visible) Qt.callLater(root.syncEditorPosition)
                onHeightChanged: if (root.visible) Qt.callLater(root.syncEditorPosition)

                Item {
                    id: subtitleSample

                    width: karaokeRow.implicitWidth + Theme.space12
                    height: karaokeRow.implicitHeight + Theme.space8
                    onWidthChanged: if (root.visible) Qt.callLater(root.syncEditorPosition)
                    onHeightChanged: if (root.visible) Qt.callLater(root.syncEditorPosition)

                    Row {
                        id: karaokeRow

                        anchors.centerIn: parent
                        spacing: 0

                        Text {
                            text: qsTr("PHỤ ĐỀ ")
                            color: "white"
                            style: Text.Outline
                            styleColor: "black"
                            font.family: karaokeFont.name
                            font.pixelSize: Math.max(12, root.draftFontSize * editorCanvas.height / (editorCanvas.height > editorCanvas.width ? 1920 : 1080))
                            font.bold: true
                            textFormat: Text.PlainText
                        }

                        Text {
                            text: qsTr("MẪU")
                            color: "#FFF200"
                            style: Text.Outline
                            styleColor: "black"
                            font.family: karaokeFont.name
                            font.pixelSize: Math.max(12, root.draftFontSize * editorCanvas.height / (editorCanvas.height > editorCanvas.width ? 1920 : 1080))
                            font.bold: true
                            textFormat: Text.PlainText
                        }
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.SizeAllCursor
                        drag.target: subtitleSample
                        drag.minimumX: 0
                        drag.maximumX: editorCanvas.width - subtitleSample.width
                        drag.minimumY: 0
                        drag.maximumY: editorCanvas.height - subtitleSample.height
                        onReleased: root.commitEditorPosition()
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space12

            Text {
                text: qsTr("Cỡ chữ")
                color: Theme.textMuted
                font.pixelSize: Theme.caption
                textFormat: Text.PlainText
            }

            AppSlider {
                Layout.fillWidth: true
                from: 10
                to: 160
                stepSize: 1
                value: root.draftFontSize
                onMoved: root.draftFontSize = Math.round(value)
                onPressedChanged: {
                    if (!pressed)
                        root.subtitleLayoutEdited(root.draftFontSize, root.draftPositionX, root.draftPositionY, root.draftBoxWidth, root.draftBoxHeight)
                }
            }

            Text {
                Layout.preferredWidth: 48
                text: qsTr("%1 px").arg(root.draftFontSize)
                color: Theme.text
                font.pixelSize: Theme.caption
                horizontalAlignment: Text.AlignRight
                textFormat: Text.PlainText
            }

            AppButton {
                text: qsTr("Đặt lại vị trí")
                compact: true
                onClicked: {
                    root.draftPositionX = 51
                    root.draftPositionY = 96
                    root.syncEditorPosition()
                    root.subtitleLayoutEdited(
                        root.draftFontSize,
                        51,
                        96,
                        root.draftBoxWidth,
                        root.draftBoxHeight
                    )
                }
            }
        }

        Item { Layout.preferredHeight: Theme.space8 }
    }

    FontLoader {
        id: karaokeFont
        source: "../../assets/fonts/Bangers-Regular.ttf"
    }
}
