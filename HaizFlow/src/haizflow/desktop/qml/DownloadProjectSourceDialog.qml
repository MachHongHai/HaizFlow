pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

AppDialog {
    id: root

    property string importMode: "single"
    readonly property bool multipleSelection: importMode === "batch"

    title: qsTr("Nhập từ dự án tải xuống")
    subtitle: multipleSelection
        ? qsTr("Chọn các video cần thêm vào dự án hàng loạt")
        : qsTr("Chọn một video đã tải")
    preferredWidth: 680
    preferredHeight: 540
    maximumWidth: 720
    maximumHeight: 680

    function openForMode(mode) {
        importMode = mode === "batch" ? "batch" : "single"
        AppController.refreshDownloadProjectSources()
        open()
    }

    ListView {
        id: sourceList

        Layout.fillWidth: true
        Layout.fillHeight: true
        model: AppController.downloadProjectSourceModel
        spacing: Theme.space4
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        reuseItems: true

        delegate: Rectangle {
            id: sourceDelegate

            required property int index
            required property string downloadItemId
            required property string downloadProjectName
            required property string downloadCategory
            required property string downloadFileName
            required property string downloadFilePath
            required property real downloadFileSize
            required property bool downloadSelected

            width: ListView.view.width
            height: 58
            radius: Theme.radiusSmall
            color: downloadSelected ? Theme.sidebarSelected : Theme.surfaceMuted
            border.width: 1
            border.color: downloadSelected ? Theme.focus : Theme.outline

            ListView.onPooled: visible = false
            ListView.onReused: visible = true

            RowLayout {
                anchors.fill: parent
                anchors.margins: Theme.space8
                spacing: Theme.space12

                FluentIcon {
                    Layout.preferredWidth: 20
                    Layout.preferredHeight: 20
                    name: "video"
                    iconColor: sourceDelegate.downloadSelected ? Theme.interactive : Theme.textMuted
                    iconSize: 18
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 1

                    Text {
                        Layout.fillWidth: true
                        text: sourceDelegate.downloadFileName
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: TypeScale.control
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                        elide: Text.ElideMiddle
                    }

                    Text {
                        Layout.fillWidth: true
                        text: sourceDelegate.downloadProjectName
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: TypeScale.metadata
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                    }
                }

                StatusBadge {
                    status: "ready"
                    label: sourceDelegate.downloadCategory === "channel"
                        ? qsTr("Kênh") : qsTr("Video")
                }

                Text {
                    Layout.preferredWidth: 64
                    text: sourceDelegate.downloadFileSize > 0
                        ? qsTr("%1 MB").arg((sourceDelegate.downloadFileSize / 1048576).toFixed(1))
                        : ""
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.metadata
                    horizontalAlignment: Text.AlignRight
                    textFormat: Text.PlainText
                }

                StudioCheckBox {
                    checked: sourceDelegate.downloadSelected
                    Accessible.name: qsTr("Chọn %1").arg(sourceDelegate.downloadFileName)
                    onToggled: AppController.setDownloadProjectSourceSelected(
                        sourceDelegate.index,
                        checked,
                        !root.multipleSelection
                    )
                }
            }
        }

        EmptyState {
            anchors.centerIn: parent
            visible: sourceList.count === 0
            width: Math.min(400, sourceList.width - Theme.space32)
            iconName: "download"
            title: qsTr("Chưa có video đã tải")
            message: qsTr("Tải video trước, sau đó quay lại để nhập vào dự án.")
        }

        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
    }

    footerActions: [
        Text {
            text: qsTr("Đã chọn: %1").arg(AppController.downloadProjectSourceSelectedCount)
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
            text: qsTr("Nhập")
            tone: "primary"
            enabled: AppController.downloadProjectSourceSelectedCount > 0
                && (root.multipleSelection
                    || AppController.downloadProjectSourceSelectedCount === 1)
            onClicked: {
                if (AppController.importSelectedDownloadProjectVideos(root.importMode))
                    root.close()
            }
        }
    ]
}
