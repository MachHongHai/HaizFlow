pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

AppDialog {
    id: root

    title: qsTr("Thêm video từ dự án")
    subtitle: qsTr("Chọn video đã dựng hoặc toàn bộ dự án hàng loạt")
    preferredWidth: 700
    preferredHeight: Math.min(560, Math.max(258, 168 + 70 * sourceModel.sourceCount))
    maximumWidth: 740
    maximumHeight: 700
    readonly property var sourceModel: AppController.tiktokProjectSourceModel

    function openForSelection() {
        searchField.text = "";
        AppController.refreshTikTokProjectSources()
        open()
    }
    onClosed: searchField.text = ""

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
            required property string videoId
            required property string projectName
            required property string projectType
            required property string fileName
            required property var model
            required property string videoSize
            required property int sourceVideoCount
            required property bool sourceSelected

            width: ListView.view.width
            height: implicitHeight
            selected: sourceSelected
            thumbnailSource: sourceDelegate.model.thumbnailSource
            label: projectName
            description: projectType === "batch" ? qsTr("%1 video đã xuất").arg(sourceVideoCount) : fileName
            badgeLabel: projectType === "batch" ? qsTr("Hàng loạt") : projectType === "manual" ? qsTr("Thủ công") : qsTr("Tự động")
            metadata: projectType === "batch" ? "" : videoSize
            onSelectionRequested: selected => AppController.setTikTokProjectSourceSelected(sourceDelegate.sourceIndex, selected)
            onSelectionFocused: sourceList.positionViewAtIndex(sourceDelegate.index, ListView.Contain)

            ListView.onPooled: visible = false
            ListView.onReused: visible = true

        }

        EmptyState {
            anchors.centerIn: parent
            visible: sourceList.count === 0
            width: Math.min(400, sourceList.width - Theme.space32)
            iconName: "video"
            title: searchField.text.length > 0 ? qsTr("Không tìm thấy video") : qsTr("Chưa có video đã dựng")
            message: searchField.text.length > 0 ? qsTr("Thử tìm bằng tên khác.")
                : qsTr("Hoàn tất dựng video trong dự án Thủ công, Tự động hoặc Hàng loạt để thêm vào đây. Không cần xuất tệp ra ngoài.")
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
            variant: "ghost"
            onClicked: root.close()
        },
        StudioButton {
            text: qsTr("Thêm video")
            variant: "primary"
            enabled: AppController.tiktokProjectSourceSelectedCount > 0
                && !AppController.socialImportBusy
            onClicked: {
                if (AppController.addSelectedTikTokProjectVideos())
                    root.close()
            }
        }
    ]
}
