import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    required property int index
    required property string fileName
    required property string status
    required property int progress
    required property string thumbnailSource
    required property string videoSize

    signal activated

    readonly property string statusLabel: status === "pending" ? qsTr("Đang chờ") : status === "processing" ? qsTr("Đang xử lý") : status === "done" ? qsTr("Hoàn tất") : status === "failed" ? qsTr("Lỗi") : status === "cancelled" ? qsTr("Đã hủy") : status === "paused" ? qsTr("Đã tạm dừng") : status === "awaiting_review" ? qsTr("Cần duyệt") : I18n.taskStateLabel(status)
    readonly property color statusColor: status === "done" ? Theme.success : status === "failed" || status === "cancelled" ? Theme.danger : status === "processing" ? Theme.warning : Theme.textMuted
    readonly property color baseColor: status === "processing" ? Theme.warmSurface : status === "awaiting_review" ? Theme.interactiveMuted : status === "failed" || status === "cancelled" ? Theme.dangerMuted : Theme.surface
    readonly property color stateOutline: status === "processing" ? Theme.amberMuted : status === "awaiting_review" ? Theme.interactiveOutline : status === "failed" || status === "cancelled" ? Theme.danger : Theme.outline

    radius: Theme.radius
    color: hoverHandler.hovered ? Theme.surfaceMuted : root.baseColor
    border.width: activeFocus ? 2 : 1
    border.color: activeFocus ? Theme.focus : hoverHandler.hovered ? Theme.outlineStrong : root.stateOutline
    focusPolicy: Qt.TabFocus
    Accessible.role: Accessible.Button
    Accessible.name: qsTr("%1, %2").arg(fileName).arg(qsTr("Chỉnh cài đặt video"))
    scale: tapHandler.pressed ? 0.99 : 1

    function resetFocusState() {
        root.focus = false;
    }

    GridView.onPooled: {
        root.visible = false;
        root.resetFocusState();
    }
    GridView.onReused: {
        root.visible = true;
        root.resetFocusState();
    }

    Keys.onReturnPressed: root.activated()
    Keys.onSpacePressed: root.activated()

    HoverHandler {
        id: hoverHandler
        cursorShape: Qt.PointingHandCursor
    }

    TapHandler {
        id: tapHandler
        onTapped: {
            root.activated();
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.round(root.width * 0.56)
            radius: Theme.radius
            color: Theme.video
            clip: true

            Image {
                id: thumbnailImage
                anchors.fill: parent
                source: root.thumbnailSource
                sourceSize.width: Math.round(root.width * 2)
                sourceSize.height: Math.round(root.width * 1.12)
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                visible: status === Image.Ready
            }

            ThumbnailFallback {
                anchors.fill: parent
                visible: root.thumbnailSource.length === 0 || thumbnailImage.status === Image.Error
            }

            Row {
                anchors.top: parent.top
                anchors.right: parent.right
                anchors.margins: Theme.space8
                spacing: Theme.space4
                visible: root.videoSize.length > 0

                Rectangle {
                    width: sizeLabel.implicitWidth + Theme.space12
                    height: 26
                    radius: Theme.radiusSmall
                    color: Theme.scrim

                    Text {
                        id: sizeLabel
                        anchors.centerIn: parent
                        text: root.videoSize
                        color: Theme.textOnDark
                        font.pixelSize: Theme.label
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                    }
                }
            }

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: 3
                color: Theme.surfaceStrong

                Rectangle {
                    width: parent.width * Math.max(0, Math.min(100, root.progress)) / 100
                    height: parent.height
                    color: root.progress >= 100 ? Theme.success : Theme.interactive
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.leftMargin: 14
            Layout.rightMargin: 14
            Layout.topMargin: 11
            Layout.bottomMargin: 11
            spacing: 7

            Text {
                Layout.fillWidth: true
                text: root.fileName
                color: Theme.text
                font.pixelSize: Theme.bodyLarge
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
                elide: Text.ElideRight
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space8

                Rectangle {
                    Layout.preferredWidth: 7
                    Layout.preferredHeight: 7
                    radius: 4
                    color: root.statusColor
                }

                Text {
                    Layout.fillWidth: true
                    text: root.statusLabel
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                }

                Text {
                    text: qsTr("%1%").arg(root.progress)
                    color: root.statusColor
                    font.pixelSize: Theme.caption
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }

                AppIcon {
                    Layout.preferredWidth: Theme.icon
                    Layout.preferredHeight: Theme.icon
                    glyph: "\uE76C"
                    iconColor: hoverHandler.hovered ? Theme.text : Theme.textSubtle
                    iconSize: Theme.iconSmall
                    Accessible.ignored: true
                }
            }
        }
    }

    transform: Translate {
        y: hoverHandler.hovered ? -2 : 0
        Behavior on y {
            NumberAnimation {
                duration: Theme.motionFast
                easing.type: Easing.OutCubic
            }
        }
    }
    Behavior on scale {
        NumberAnimation {
            duration: Theme.motionFast
            easing.type: Easing.OutCubic
        }
    }
}
