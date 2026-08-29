pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

AppDialog {
    id: root

    title: qsTr("Thêm video từ dự án")
    subtitle: qsTr("Chọn video đã xử lý hoặc toàn bộ dự án hàng loạt")
    preferredWidth: 700
    preferredHeight: 560
    maximumWidth: 740
    maximumHeight: 700

    function openForSelection() {
        AppController.refreshTikTokProjectSources()
        open()
    }

    ListView {
        id: sourceList

        Layout.fillWidth: true
        Layout.fillHeight: true
        model: AppController.tiktokProjectSourceModel
        spacing: Theme.space4
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        reuseItems: true

        delegate: Rectangle {
            id: sourceDelegate

            required property int index
            required property string videoId
            required property string projectName
            required property string projectType
            required property string fileName
            required property string thumbnailSource
            required property string videoSize
            required property int sourceVideoCount
            required property bool sourceSelected

            width: ListView.view.width
            height: 66
            radius: Theme.radiusSmall
            color: sourceSelected ? Theme.sidebarSelected : Theme.surfaceMuted
            border.width: 1
            border.color: sourceSelected ? Theme.focus : Theme.outline

            ListView.onPooled: visible = false
            ListView.onReused: visible = true

            RowLayout {
                anchors.fill: parent
                anchors.margins: Theme.space8
                spacing: Theme.space12

                MediaThumbnail {
                    Layout.preferredWidth: 84
                    Layout.fillHeight: true
                    source: sourceDelegate.thumbnailSource
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 1

                    Text {
                        Layout.fillWidth: true
                        text: sourceDelegate.projectName
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: TypeScale.control
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                    }

                    Text {
                        Layout.fillWidth: true
                        text: sourceDelegate.projectType === "batch"
                            ? qsTr("%1 video sẵn sàng").arg(sourceDelegate.sourceVideoCount)
                            : sourceDelegate.fileName
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: TypeScale.metadata
                        textFormat: Text.PlainText
                        elide: Text.ElideMiddle
                    }
                }

                StatusBadge {
                    status: "ready"
                    label: sourceDelegate.projectType === "batch"
                        ? qsTr("Hàng loạt") : qsTr("Tự động")
                }

                Text {
                    Layout.preferredWidth: 72
                    text: sourceDelegate.projectType === "batch"
                        ? qsTr("%1 video").arg(sourceDelegate.sourceVideoCount)
                        : sourceDelegate.videoSize
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.metadata
                    horizontalAlignment: Text.AlignRight
                    textFormat: Text.PlainText
                }

                StudioCheckBox {
                    checked: sourceDelegate.sourceSelected
                    Accessible.name: qsTr("Chọn dự án %1").arg(sourceDelegate.projectName)
                    onToggled: AppController.setTikTokProjectSourceSelected(
                        sourceDelegate.index,
                        checked
                    )
                }
            }
        }

        EmptyState {
            anchors.centerIn: parent
            visible: sourceList.count === 0
            width: Math.min(400, sourceList.width - Theme.space32)
            iconName: "video"
            title: qsTr("Chưa có video hoàn tất")
            message: qsTr("Xử lý video trong dự án Tự động hoặc Hàng loạt trước.")
        }

        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
    }

    footerActions: [
        Text {
            text: qsTr("Đã chọn: %1").arg(AppController.tiktokProjectSourceSelectedCount)
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.metadata
            verticalAlignment: Text.AlignVCenter
        },
        Item { Layout.preferredWidth: Theme.space8 },
        StudioButton {
            text: qsTr("Hủy")
            tone: "secondary"
            onClicked: root.close()
        },
        StudioButton {
            text: qsTr("Thêm video")
            tone: "primary"
            enabled: AppController.tiktokProjectSourceSelectedCount > 0
                && !AppController.tiktokPublishBusy
            onClicked: {
                if (AppController.addSelectedTikTokProjectVideos())
                    root.close()
            }
        }
    ]
}
