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
    property alias searchText: searchField.text
    readonly property var visibleVideos: searchField.text.trim().length === 0 ? videos
        : videos.filter(video => normalise(String(video.name || "")).includes(normalise(searchField.text.trim())))
    readonly property var targetIds: scope === "selection" ? selectedIds
        : videos.filter(video => scope === "all" || video.status !== "done").map(video => video.videoId)
    spacing: Theme.space8

    function toggleVideo(videoId, checked) {
        root.selectedIds = checked ? [...new Set([...root.selectedIds, videoId])]
            : root.selectedIds.filter(id => id !== videoId);
    }

    function normalise(value) {
        return value.toLowerCase().replace(/đ/g, "d").normalize("NFD").replace(/[\u0300-\u036f]/g, "");
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
    AppTextField {
        id: searchField
        objectName: "batchScopeSearch"
        Layout.fillWidth: true
        visible: root.scope === "selection" && (root.videos.length >= 8 || text.length > 0)
        placeholderText: qsTr("Tìm video")
        accessibleName: placeholderText
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
            text: searchField.text.trim().length > 0 ? qsTr("Chọn kết quả") : qsTr("Chọn tất cả")
            variant: "ghost"
            enabled: root.visibleVideos.length > 0
            onClicked: root.selectedIds = [...new Set([...root.selectedIds, ...root.visibleVideos.map(video => video.videoId)])]
        }
        StudioButton {
            visible: root.scope === "selection"
            text: qsTr("Bỏ chọn")
            variant: "ghost"
            onClicked: root.selectedIds = []
        }
    }
    Text {
        Layout.fillWidth: true
        visible: searchField.visible && root.visibleVideos.length === 0
        text: qsTr("Không tìm thấy video")
        color: Theme.textMuted
        font.pixelSize: TypeScale.metadata
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
        model: root.scope === "selection" ? root.visibleVideos : []
        spacing: Theme.space4
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
        delegate: VideoSelectionRow {
            id: card
            required property int index
            required property var modelData
            readonly property string videoId: String(modelData.videoId)
            badgeState: modelData.status === "pending" && modelData.step === "queued" ? "queued"
                : String(modelData.status || "pending")
            badgeLabel: TaskPresentation.label(badgeState)
            label: String(modelData.name || "")
            selected: root.selectedIds.includes(videoId)
            thumbnailSource: modelData.thumbnailSource || ""
            width: list.width - Theme.space16
            height: implicitHeight
            onSelectionFocused: list.positionViewAtIndex(card.index, ListView.Contain)
            onSelectionRequested: selected => root.toggleVideo(card.videoId, selected)
        }
    }
}
