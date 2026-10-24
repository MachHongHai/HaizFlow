pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

AppDialog {
    id: root
    property bool overrides: false
    property var rows: []
    title: overrides ? qsTr("Cài đặt riêng") : qsTr("Kết quả hàng loạt")
    subtitle: overrides ? qsTr("Các video này vẫn được xử lý với cài đặt riêng") : qsTr("Chi tiết theo từng video")
    preferredWidth: 700
    maximumHeight: 680

    function fieldLabel(key) {
        switch (key) {
        case "workflowMode": case "workflow": return qsTr("Chế độ xử lý");
        case "outputFormat": return qsTr("Khung hình đầu ra");
        case "targetLanguage": return qsTr("Ngôn ngữ đích");
        case "speechRecognitionModel": return qsTr("Model nhận dạng");
        case "translationModel": return qsTr("Model dịch");
        case "geminiTranslationInstructions": return qsTr("Hướng dẫn dịch");
        case "geminiTranslationGlossary": return qsTr("Tên nhân vật và xưng hô");
        case "geminiTranslationStyle": return qsTr("Văn phong dịch");
        case "ttsProvider": return qsTr("Model giọng đọc");
        case "ttsVoice": case "voice": return qsTr("Giọng đọc");
        case "speakerMode": case "speakers": return qsTr("Người nói");
        case "enableAudioSeparation": case "audioSource": return qsTr("Tách giọng");
        case "originalVolume": case "sourceVolume": return qsTr("Âm lượng nguồn");
        case "backgroundMusicVolume": return qsTr("Âm lượng nhạc nền");
        case "ttsVolume": return qsTr("Âm lượng giọng đọc");
        case "backgroundMusicPath": case "backgroundMusic": return qsTr("Nhạc nền");
        case "backgroundMusicLoop": return qsTr("Lặp nhạc nền");
        case "audioDuckingEnabled": case "audioDuckingReductionDb": return qsTr("Giảm âm khi có giọng đọc");
        case "voiceReferencePath": return qsTr("Giọng nhân bản");
        case "removeOriginalSubtitles": case "originalSubtitles": return qsTr("Che phụ đề");
        case "originalSubtitleRemovalMode": case "subtitleRemovalMode": return qsTr("Cách che phụ đề");
        case "originalSubtitleRegion": return qsTr("Vùng che phụ đề gốc");
        case "subtitleStyle": case "subtitleLayout": return qsTr("Kiểu và vị trí phụ đề");
        case "outputSpeed": return qsTr("Tốc độ đầu ra");
        case "watermarkText": return qsTr("Nội dung watermark");
        case "watermarkKind": return qsTr("Loại watermark");
        case "watermarkImagePath": return qsTr("Ảnh watermark");
        case "watermarkVideoPath": return qsTr("Video watermark");
        case "watermarkScalePercent": return qsTr("Kích thước watermark");
        case "watermarkOpacityPercent": return qsTr("Độ trong suốt watermark");
        case "watermarkOutlinePercent": return qsTr("Viền watermark");
        case "watermarkFontFamily": return qsTr("Font watermark");
        case "watermarkTextColor": return qsTr("Màu watermark");
        case "watermarkBold": return qsTr("Watermark in đậm");
        case "watermarkItalic": return qsTr("Watermark in nghiêng");
        case "watermark": return qsTr("Watermark");
        default: return key;
        }
    }
    function differences(keys) {
        const labels = (keys || []).map(key => fieldLabel(key));
        return labels.filter((label, index) => labels.indexOf(label) === index).join(" · ");
    }
    function statusLabel(status) {
        switch (status) {
        case "done": return qsTr("Thành công");
        case "failed": return qsTr("Lỗi");
        case "cancelled": return qsTr("Đã hủy");
        case "paused": return qsTr("Đã tạm dừng");
        case "awaiting_review": return qsTr("Chờ duyệt phụ đề");
        case "processing": case "rendering": case "exporting": return qsTr("Đang xử lý");
        default: return qsTr("Đang chờ");
        }
    }

    ListView {
        id: details
        Layout.fillWidth: true
        Layout.preferredHeight: Math.min(420, contentHeight)
        clip: true
        spacing: Theme.space12
        model: root.rows
        reuseItems: true
        delegate: Rectangle {
            id: row
            required property var modelData
            width: details.width
            height: rowContent.implicitHeight + Theme.space24
            radius: Theme.radiusSmall
            color: Theme.surfaceElevated
            ColumnLayout {
                id: rowContent
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: Theme.space12
                spacing: Theme.space8
                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        Layout.fillWidth: true
                        text: row.modelData.fileName || ""
                        textFormat: Text.PlainText
                        color: Theme.text
                        font.pixelSize: TypeScale.control
                        font.weight: Font.DemiBold
                        elide: Text.ElideMiddle
                    }
                    Text {
                        visible: !root.overrides
                        text: root.statusLabel(row.modelData.status)
                        color: row.modelData.status === "failed" ? Theme.danger : Theme.textMuted
                        font.pixelSize: TypeScale.label
                    }
                }
                TextEdit {
                    Layout.fillWidth: true
                    visible: text.length > 0
                    text: root.overrides ? root.differences(row.modelData.differences) : (row.modelData.error || "")
                    textFormat: TextEdit.PlainText
                    readOnly: true
                    selectByMouse: true
                    wrapMode: TextEdit.Wrap
                    color: root.overrides ? Theme.warning : Theme.danger
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.metadata
                }
            }
        }
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
    }
    footerActions: [
        StudioButton { text: qsTr("Đóng"); variant: "primary"; onClicked: root.close() }
    ]
}
