pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

AppDialog {
    id: root

    property string importMode: "single"
    readonly property bool multipleSelection: importMode === "batch"
    readonly property var sourceModel: AppController.downloadProjectSourceModel

    title: qsTr("Nhập từ dự án tải xuống")
    subtitle: multipleSelection
        ? qsTr("Chọn các video cần thêm vào dự án hàng loạt")
        : qsTr("Chọn một video đã tải")
    preferredWidth: 680
    preferredHeight: Math.min(560, Math.max(258, 168 + 70 * sourceModel.sourceCount))
    maximumWidth: 720
    maximumHeight: 680

    function openForMode(mode) {
        searchField.text = "";
        importMode = mode === "batch" ? "batch" : "single"
        AppController.refreshDownloadProjectSources()
        open()
    }
    onClosed: {
        root.sourceModel.stopThumbnails();
        searchField.text = "";
    }

    AppTextField {
        id: searchField
        objectName: "videoSourceSearch"
        Layout.fillWidth: true
        visible: root.sourceModel.sourceCount >= 8 || text.length > 0
        placeholderText: qsTr("Tìm tên dự án hoặc video")
        accessibleName: placeholderText
        onTextChanged: root.sourceModel.setSearch(text)
    }

    ListView {
        id: sourceList

        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.minimumHeight: 0
        model: root.sourceModel
        spacing: Theme.space4
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        reuseItems: true

        delegate: VideoSelectionRow {
            id: sourceDelegate

            required property int index
            required property int sourceIndex
            required property var model
            required property string downloadProjectName
            required property string downloadCategory
            required property string downloadFileName
            required property real downloadFileSize
            required property bool downloadSelected

            width: ListView.view.width
            height: implicitHeight
            selected: downloadSelected
            thumbnailSource: sourceDelegate.model.thumbnailSource
            label: downloadFileName
            description: downloadProjectName
            badgeLabel: downloadCategory === "channel" ? qsTr("Kênh") : qsTr("Video")
            metadata: downloadFileSize > 0 ? qsTr("%1 MB").arg((downloadFileSize / 1048576).toLocaleString(Qt.locale(), "f", 1)) : ""
            onSelectionRequested: selected => AppController.setDownloadProjectSourceSelected(
                                     sourceDelegate.sourceIndex, selected, !root.multipleSelection)
            onSelectionFocused: sourceList.positionViewAtIndex(sourceDelegate.index, ListView.Contain)
            Component.onCompleted: root.sourceModel.requestThumbnail(sourceIndex)

            ListView.onPooled: visible = false
            ListView.onReused: {
                visible = true;
                root.sourceModel.requestThumbnail(sourceIndex);
            }
        }

        EmptyState {
            anchors.centerIn: parent
            visible: sourceList.count === 0
            width: Math.min(400, sourceList.width - Theme.space32)
            iconName: "download"
            title: searchField.text.length > 0 ? qsTr("Không tìm thấy video") : qsTr("Chưa có video đã tải")
            message: searchField.text.length > 0 ? qsTr("Thử tìm bằng tên khác.")
                : qsTr("Tải video trước, sau đó quay lại để nhập vào dự án.")
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
            variant: "ghost"
            onClicked: root.close()
        },
        StudioButton {
            text: qsTr("Nhập")
            variant: "primary"
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
