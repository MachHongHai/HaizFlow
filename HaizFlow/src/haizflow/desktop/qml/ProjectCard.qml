import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    required property int index
    required property string projectName
    required property string projectType
    required property int videoCount
    required property string status
    required property int progress
    required property string thumbnailSource
    required property string videoSize

    signal activated
    signal openRequested
    signal projectFolderRequested
    signal deleteRequested

    readonly property string statusLabel: status === "pending" ? qsTr("Đang chờ") : status === "empty" ? qsTr("Chưa chọn video nguồn") : status === "ready" || status === "manual_ready" ? qsTr("Sẵn sàng") : status === "processing" ? qsTr("Đang xử lý") : status === "done" ? qsTr("Hoàn tất") : status === "failed" ? qsTr("Lỗi") : status === "cancelled" ? qsTr("Đã hủy") : status === "paused" ? qsTr("Đã tạm dừng") : status === "awaiting_review" ? qsTr("Cần duyệt") : I18n.taskStateLabel(status)
    readonly property string typeLabel: projectType === "manual" ? qsTr("Thủ công")
        : projectType === "batch" ? qsTr("Hàng loạt")
        : projectType === "download" ? qsTr("Tải xuống")
        : projectType === "publish" ? qsTr("Đăng mạng xã hội") : qsTr("Tự động")
    readonly property color statusColor: status === "done" ? Theme.success : status === "failed" || status === "cancelled" ? Theme.danger : status === "processing" ? Theme.warning : status === "awaiting_review" || status === "manual_ready" ? Theme.interactive : Theme.textMuted

    height: Math.round(width * 0.56 + 64)
    radius: Theme.radius
    color: hoverHandler.hovered ? Theme.surfaceMuted : Theme.surface
    border.width: activeFocus ? 2 : 1
    border.color: activeFocus ? Theme.focus : hoverHandler.hovered ? Theme.outlineStrong : Theme.outline
    focusPolicy: Qt.TabFocus
    Accessible.role: Accessible.Button
    Accessible.name: projectName
    scale: tapHandler.pressed ? 0.99 : 1

    function resetFocusState() {
        root.focus = false;
        projectContextMenu.close();
    }

    Keys.onReturnPressed: root.activated()
    Keys.onSpacePressed: root.activated()

    HoverHandler {
        id: hoverHandler
        cursorShape: Qt.PointingHandCursor
    }

    TapHandler {
        id: tapHandler

        acceptedButtons: Qt.LeftButton
        onTapped: {
            root.activated();
        }
    }

    TapHandler {
        acceptedButtons: Qt.RightButton
        onTapped: function (eventPoint) {
            root.forceActiveFocus();
            const position = root.mapToItem(Overlay.overlay, eventPoint.position.x, eventPoint.position.y);
            projectContextMenu.x = Math.round(position.x);
            projectContextMenu.y = Math.round(position.y);
            projectContextMenu.open();
        }
    }

    Menu {
        id: projectContextMenu

        parent: Overlay.overlay
        width: 224
        padding: Theme.space4
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            radius: Theme.radiusSmall
            color: Theme.surfaceElevated
            border.width: 1
            border.color: Theme.outlineStrong
        }

        AppMenuItem {
            text: qsTr("Mở dự án")
            iconGlyph: "\uE8A7"
            onTriggered: root.openRequested()
        }

        AppMenuItem {
            text: qsTr("Mở thư mục dự án")
            iconGlyph: "\uE8B7"
            onTriggered: root.projectFolderRequested()
        }

        MenuSeparator {}

        AppMenuItem {
            text: qsTr("Xóa dự án")
            iconGlyph: "\uE74D"
            tone: "danger"
            onTriggered: root.deleteRequested()
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
                visible: root.projectType !== "download" && root.projectType !== "publish" && (root.thumbnailSource.length === 0 || thumbnailImage.status === Image.Error)
            }

            AppIcon {
                anchors.centerIn: parent
                visible: root.projectType === "download" || root.projectType === "publish"
                width: 42
                height: 42
                glyph: root.projectType === "publish" ? "\uE768" : "\uE896"
                iconColor: Theme.interactive
                iconSize: 42
            }

            Rectangle {
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.margins: Theme.space8
                visible: true
                implicitWidth: batchLabel.implicitWidth + 16
                implicitHeight: 24
                radius: Theme.radiusTiny
                color: Theme.surfaceStrong

                Text {
                    id: batchLabel
                    anchors.centerIn: parent
                    text: root.typeLabel
                    color: Theme.text
                    font.pixelSize: Theme.label
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }
            }

            Rectangle {
                anchors.top: parent.top
                anchors.right: parent.right
                anchors.margins: Theme.space8
                visible: (root.projectType === "single" || root.projectType === "manual") && root.videoSize.length > 0
                implicitWidth: sizeLabel.implicitWidth + Theme.space12
                implicitHeight: 26
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

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: 3
                visible: root.projectType !== "download" && root.projectType !== "publish"
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
                text: root.projectName
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
                    text: root.projectType === "batch"
                        ? qsTr("%1 - %2").arg(root.videoCount).arg(qsTr("video"))
                        : root.projectType === "publish"
                            ? qsTr("%1 - %2").arg(root.videoCount).arg(qsTr("bài đăng"))
                            : root.statusLabel
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                }

                Text {
                    visible: root.projectType !== "download" && root.projectType !== "publish"
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
