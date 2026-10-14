pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

GridLayout {
    id: root
    property string outputFormat: "keep_ratio"
    property bool editable: true
    property bool compact: false
    property bool showSpeed: false
    property real outputSpeed: 1.0
    signal speedEdited(real value)
    signal edited(string value)
    readonly property string description: root.outputFormat === "blur_background_9_16"
        ? qsTr("Giữ trọn video ở giữa khung 1080 × 1920, lấp khoảng trống bằng nền mờ. Nguồn đã đúng 9:16 giữ nguyên kích thước.")
        : root.outputFormat === "tiktok_9_16_crop"
            ? qsTr("Phóng đầy khung 1080 × 1920; nội dung ngoài khung có thể bị cắt. Nguồn đã đúng 9:16 giữ nguyên kích thước.")
            : qsTr("Giữ khung hình của video nguồn. Không thêm nền hoặc cắt theo tỷ lệ đăng mạng xã hội.")
    columns: root.compact ? (root.showSpeed ? 4 : 3) : 1
    columnSpacing: Theme.space8
    rowSpacing: Theme.space8

    SettingLabel {
        Layout.fillWidth: !root.compact
        text: qsTr("Khung hình đầu ra")
        helpText: root.compact ? root.description : ""
    }
    OutputFrameCombo {
        Layout.preferredWidth: implicitWidth
        Layout.maximumWidth: implicitWidth
        Layout.alignment: Qt.AlignLeft
        enabled: root.editable
        outputFormat: root.outputFormat
        onEdited: function(value) { root.edited(value); }
    }
    Item {
        visible: root.compact
        Layout.fillWidth: true
    }
    OutputSpeedButton {
        visible: root.showSpeed
        enabled: root.editable
        speed: root.outputSpeed
        compactLabel: true
        onEdited: function(value) { root.speedEdited(value); }
    }
    Text {
        visible: !root.compact
        Layout.fillWidth: true
        Layout.preferredWidth: 0
        Layout.minimumWidth: 0
        text: root.description
        color: root.outputFormat === "tiktok_9_16_crop" ? Theme.warning : Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.label
        wrapMode: Text.WordWrap
    }
}
