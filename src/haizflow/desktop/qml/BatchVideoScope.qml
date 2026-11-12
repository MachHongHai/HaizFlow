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
        visible: root.scope === "selection"
        Layout.fillWidth: true
        Layout.preferredHeight: Math.min(240, contentHeight)
        clip: true
        reuseItems: true
        model: root.videos
        spacing: Theme.space4
        ScrollBar.vertical: ScrollBar {}
        delegate: AppCheckBox {
            required property var modelData
            width: list.width - Theme.space16
            text: String(modelData.name || "")
                + (modelData.status === "done" ? qsTr(" · Hoàn tất") : "")
            checked: root.selectedIds.includes(modelData.videoId)
            onToggled: root.selectedIds = checked
                ? root.selectedIds.concat([modelData.videoId])
                : root.selectedIds.filter(id => id !== modelData.videoId)
        }
    }
}
