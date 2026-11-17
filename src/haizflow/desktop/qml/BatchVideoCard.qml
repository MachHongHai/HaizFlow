pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Control {
    id: root
    objectName: "batchVideoCard_" + index

    required property int index
    required property string fileName
    required property string status
    required property int progress
    required property string thumbnailSource
    required property string videoSize
    property bool customSettings: false
    property bool removalEnabled: false

    signal activated
    signal removalRequested

    readonly property string statusLabel: status === "pending" ? qsTr("Đang chờ") : status === "processing" ? qsTr("Đang xử lý") : status === "done" ? qsTr("Hoàn tất") : status === "failed" ? qsTr("Lỗi") : status === "cancelled" ? qsTr("Đã hủy") : status === "paused" ? qsTr("Đã tạm dừng") : status === "awaiting_review" ? qsTr("Cần duyệt") : I18n.taskStateLabel(status)
    readonly property color statusColor: status === "done" ? Theme.success : status === "failed" ? Theme.danger : status === "processing" || status === "awaiting_review" ? Theme.warning : Theme.textMuted

    background: Rectangle {
        radius: Theme.radius
        color: hoverHandler.hovered ? Theme.surfaceMuted : Theme.surfaceElevated
        border.width: root.visualFocus ? 2 : 1
        border.color: root.visualFocus ? Theme.controlFocus : hoverHandler.hovered ? Theme.outlineStrong : Theme.divider
    }
    focusPolicy: Qt.TabFocus
    Accessible.role: Accessible.Button
    Accessible.name: qsTr("%1, %2").arg(fileName).arg(qsTr("Chỉnh cài đặt video"))
    Accessible.description: root.customSettings ? qsTr("%1, cài đặt riêng").arg(root.statusLabel) : root.statusLabel
    ToolTip.visible: hoverHandler.hovered && fileNameLabel.truncated && !tapHandler.pressed
    ToolTip.delay: 700
    ToolTip.text: root.fileName

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

            Rectangle {
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.margins: Theme.space8
                width: numberLabel.implicitWidth + Theme.space12
                height: 24
                radius: Theme.radiusSmall
                color: Theme.scrim
                Text {
                    id: numberLabel
                    anchors.centerIn: parent
                    text: String(root.index + 1).padStart(2, "0")
                    color: Theme.textOnDark
                    font.pixelSize: TypeScale.metadata
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }
            }

            Rectangle {
                visible: root.customSettings
                anchors.top: parent.top
                anchors.right: parent.right
                anchors.margins: Theme.space8
                width: overrideLabel.implicitWidth + Theme.space12
                height: 24
                radius: Theme.radiusSmall
                color: Theme.scrim
                Text {
                    id: overrideLabel
                    anchors.centerIn: parent
                    text: qsTr("Cài đặt riêng")
                    color: Theme.textOnDark
                    font.pixelSize: Theme.label
                    textFormat: Text.PlainText
                }
            }

            Rectangle {
                visible: root.status === "processing" || root.status === "done"
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
            Layout.leftMargin: Theme.space12
            Layout.rightMargin: Theme.space12
            Layout.topMargin: Theme.space12
            Layout.bottomMargin: Theme.space8
            spacing: Theme.space4

            Text {
                id: fileNameLabel
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                Layout.minimumHeight: 40
                Layout.maximumHeight: 40
                text: root.fileName
                color: Theme.text
                font.pixelSize: Theme.bodyLarge
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
                elide: Text.ElideRight
                wrapMode: Text.Wrap
                maximumLineCount: 2
                verticalAlignment: Text.AlignTop
            }

            Text {
                id: sizeLabel
                Layout.fillWidth: true
                text: root.videoSize.length > 0 ? root.videoSize : qsTr("Video")
                color: Theme.textSubtle
                font.pixelSize: TypeScale.metadata
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
                    color: root.statusColor
                    font.pixelSize: Theme.caption
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                }

                Text {
                    visible: root.status === "processing"
                    text: qsTr("%1%").arg(root.progress)
                    color: root.statusColor
                    font.pixelSize: Theme.caption
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }

                AppIcon {
                    visible: !root.removalEnabled
                    Layout.preferredWidth: Theme.icon
                    Layout.preferredHeight: Theme.icon
                    glyph: "\uE76C"
                    iconColor: hoverHandler.hovered ? Theme.text : Theme.textSubtle
                    iconSize: Theme.iconSmall
                    Accessible.ignored: true
                }
                IconButton {
                    objectName: "batchVideoRemove_" + root.index
                    visible: root.removalEnabled
                    glyph: IconCatalog.glyph("delete")
                    toolTipText: qsTr("Xóa video")
                    controlSize: 32
                    onClicked: root.removalRequested()
                }
            }
        }
    }
}
