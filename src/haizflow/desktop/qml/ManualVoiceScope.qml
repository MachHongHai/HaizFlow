pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root
    property var segments: []
    property string currentSegmentId: ""
    property string scope: "all"
    property var selectedIds: []
    property real cueListHeight: 260
    readonly property int currentSegmentIndex: currentSegmentId.length > 0
        ? segments.findIndex(item => String(item.segment_id || "") === currentSegmentId) : -1
    readonly property var currentSegment: currentSegmentIndex >= 0 ? segments[currentSegmentIndex] : null
    readonly property bool valid: segments.length > 0 && (scope === "all" || (scope === "segment" ? currentSegment !== null : selectedIds.length > 0))
    spacing: Theme.space8

    function targetIds() {
        return scope === "all" ? [] : scope === "segment" ? [currentSegmentId] : selectedIds.slice();
    }
    function reset(items, segmentId) {
        scope = "all";
        segments = items;
        currentSegmentId = String(segmentId || "");
        selectedIds = currentSegment ? [currentSegmentId] : [];
        sentences.selectedIndex = segments.findIndex(item => String(item.segment_id || "") === currentSegmentId);
        sentences.resetSearch();
    }
    function toggle(segmentId) {
        selectedIds = selectedIds.includes(segmentId) ? selectedIds.filter(id => id !== segmentId) : selectedIds.concat([segmentId]);
    }

    SettingLabel {
        text: qsTr("Phạm vi")
    }
    StudioComboBox {
        objectName: "manualVoiceScope"
        Layout.fillWidth: true
        model: [
            {
                label: qsTr("Toàn bộ"),
                value: "all"
            },
            {
                label: qsTr("Câu này"),
                value: "segment"
            },
            {
                label: qsTr("Chọn câu…"),
                value: "selection"
            }
        ]
        textRole: "label"
        valueRole: "value"
        currentIndex: root.scope === "segment" ? 1 : root.scope === "selection" ? 2 : 0
        onActivated: root.scope = String(currentValue)
        Accessible.name: qsTr("Phạm vi tạo giọng")
    }
    Rectangle {
        Layout.fillWidth: true
        implicitHeight: currentCueContent.implicitHeight + Theme.space24
        visible: root.scope === "segment" && root.currentSegment !== null
        color: Theme.input
        radius: Theme.radiusSmall
        border.color: Theme.outline
        ColumnLayout {
            id: currentCueContent
            anchors.fill: parent
            anchors.margins: Theme.space12
            spacing: Theme.space4
            Text {
                objectName: "manualVoiceCurrentCueTime"
                Layout.fillWidth: true
                text: root.currentSegment ? String(root.currentSegmentIndex + 1).padStart(2, "0") + "  "
                    + sentences.formatTime(root.currentSegment.start) + " — " + sentences.formatTime(root.currentSegment.end) : ""
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.metadata
                textFormat: Text.PlainText
            }
            Text {
                objectName: "manualVoiceCurrentCueText"
                Layout.fillWidth: true
                text: root.currentSegment ? String(root.currentSegment.text || "") : ""
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.section
                wrapMode: Text.Wrap
                textFormat: Text.PlainText
            }
        }
    }
    Text {
        Layout.fillWidth: true
        visible: root.scope === "segment" && root.currentSegment === null
        text: qsTr("Chọn một câu trên timeline hoặc danh sách phụ đề.")
        color: Theme.textMuted
        font.pixelSize: Theme.body
        wrapMode: Text.Wrap
        textFormat: Text.PlainText
    }
    ColumnLayout {
        visible: root.scope === "selection"
        Layout.fillWidth: true
        spacing: Theme.space8
        RowLayout {
            Layout.fillWidth: true
            Text {
                objectName: "manualVoiceSelectionCount"
                Layout.fillWidth: true
                text: qsTr("Đã chọn %1 / %2 câu").arg(root.selectedIds.length).arg(root.segments.length)
                color: Theme.textMuted
                font.pixelSize: TypeScale.metadata
                textFormat: Text.PlainText
            }
            StudioButton {
                text: qsTr("Chọn tất cả")
                onClicked: root.selectedIds = root.segments.map(item => String(item.segment_id || ""))
            }
            StudioButton {
                text: qsTr("Bỏ chọn")
                onClicked: root.selectedIds = []
            }
        }
        SubtitleCueList {
            id: sentences
            objectName: "manualVoiceSentenceList"
            Layout.fillWidth: true
            Layout.preferredHeight: root.cueListHeight
            multiSelect: true
            segments: root.segments
            checkedSegmentIds: root.selectedIds
            onSegmentSelected: index => selectedIndex = index
            onSegmentToggled: index => root.toggle(String(root.segments[index].segment_id || ""))
        }
    }
}
