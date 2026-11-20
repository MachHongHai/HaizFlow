pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root
    objectName: "batchScope"
    property var videos: []
    property string scope: "unfinished"
    property var selectedIds: []
    readonly property var targetIds: scope === "selection" ? selectedIds
        : videos.filter(video => scope === "all" || video.status !== "done").map(video => video.videoId)
    spacing: Theme.space8

    function toggleVideo(videoId, checked) {
        root.selectedIds = checked ? root.selectedIds.concat([videoId]) : root.selectedIds.filter(id => id !== videoId);
    }

    SettingLabel { text: qsTr("Phạm vi") }
    StudioComboBox {
        objectName: "batchVideoScope"
        Layout.fillWidth: true
        model: [{value: "unfinished", label: qsTr("Video chưa hoàn tất")},
            {value: "all", label: qsTr("Toàn bộ")},
            {value: "selection", label: qsTr("Chọn video…")}]
        textRole: "label"
        valueRole: "value"
        currentIndex: root.scope === "all" ? 1 : root.scope === "selection" ? 2 : 0
        onActivated: root.scope = String(currentValue)
        Accessible.name: qsTr("Phạm vi xử lý video")
    }
    RowLayout {
        Layout.fillWidth: true
        Text {
            Layout.fillWidth: true
            text: qsTr("%1 / %2 video").arg(root.targetIds.length).arg(root.videos.length)
            color: Theme.textMuted
            font.pixelSize: TypeScale.metadata
        }
        StudioButton {
            visible: root.scope === "selection"
            text: qsTr("Chọn tất cả")
            variant: "ghost"
            onClicked: root.selectedIds = root.videos.map(video => video.videoId)
        }
        StudioButton {
            visible: root.scope === "selection"
            text: qsTr("Bỏ chọn")
            variant: "ghost"
            onClicked: root.selectedIds = []
        }
    }
    ListView {
        id: list
        objectName: "batchScopeVideoList"
        visible: root.scope === "selection"
        Layout.fillWidth: true
        Layout.preferredHeight: Math.min(276, contentHeight)
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        reuseItems: true
        model: root.scope === "selection" ? root.videos : []
        spacing: Theme.space4
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
        delegate: Rectangle {
            id: card
            required property int index
            required property var modelData
            readonly property string videoId: String(modelData.videoId)
            readonly property string videoName: String(modelData.name || "")
            readonly property string status: String(modelData.status || "pending")
            readonly property string statusLabel: status === "done" ? qsTr("Hoàn tất")
                : status === "failed" ? qsTr("Lỗi") : status === "paused" ? qsTr("Đã tạm dừng")
                : status === "cancelled" ? qsTr("Đã hủy") : status === "awaiting_review" ? qsTr("Cần duyệt")
                : status === "processing" ? qsTr("Đang xử lý") : qsTr("Đang chờ")
            readonly property bool selected: root.selectedIds.includes(videoId)
            width: list.width - Theme.space16
            height: 66
            radius: Theme.radiusSmall
            color: selected ? Theme.sidebarSelected : Theme.surfaceMuted
            border.width: 1
            border.color: selected ? Theme.outlineStrong : Theme.outline

            RowLayout {
                anchors.fill: parent
                anchors.margins: Theme.space8
                spacing: Theme.space12

                MediaThumbnail {
                    objectName: "batchScopeThumbnail"
                    Layout.preferredWidth: 84
                    Layout.fillHeight: true
                    source: card.modelData.thumbnailSource || ""
                    Accessible.ignored: true
                }
                Text {
                    Layout.fillWidth: true
                    text: card.videoName
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.control
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                    elide: Text.ElideMiddle
                }
                StatusBadge { status: card.status; label: card.statusLabel }
                StudioCheckBox {
                    objectName: "batchScopeRowCheckBox"
                    checked: card.selected
                    Accessible.name: qsTr("Chọn video %1").arg(card.videoName)
                    Accessible.description: card.statusLabel
                    onActiveFocusChanged: if (activeFocus) list.positionViewAtIndex(card.index, ListView.Contain)
                    onToggled: root.toggleVideo(card.videoId, checked)
                }
            }
        }
    }
}
