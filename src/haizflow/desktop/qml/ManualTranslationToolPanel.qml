pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root
    property var inspector
    spacing: Theme.space8
    readonly property int warningCount: root.inspector.subtitleSegments.filter(function(segment) {
        return (segment.translation_warnings || []).length > 0
            && String(segment.translation_warning_text || "") === String(segment.text || "");
    }).length
    InlineBanner {
        Layout.fillWidth: true
        visible: root.warningCount > 0
        tone: "warning"
        message: qsTr("Đã áp dụng bản dịch. Có %1 câu cần kiểm tra trong Phụ đề.").arg(root.warningCount)
    }
    Text {
        Layout.fillWidth: true
        text: AppController.processingDevice === "gpu"
            ? qsTr("Máy đang dùng GPU. Model GPU thường xử lý nhanh hơn; bạn vẫn có thể chọn CPU.")
            : qsTr("Chế độ CPU: model GPU chưa khả dụng. Đổi bộ xử lý trong Cài đặt → Chung để sử dụng GPU.")
        color: Theme.textMuted
        font.pixelSize: TypeScale.metadata
        wrapMode: Text.Wrap
        textFormat: Text.PlainText
    }
    SettingLabel {
        Layout.fillWidth: true
        text: qsTr("Model nhận dạng")
        helpText: qsTr("Turbo cần GPU. Small dùng ít bộ nhớ hơn và hỗ trợ CPU.")
    }
    AppComboBox {
        Layout.fillWidth: true
        enabled: root.inspector.editable
        textRole: "label"
        valueRole: "value"
        model: AppController.speechRecognitionModelOptions
        currentIndex: AppController.speechRecognitionModelIndex
        onActivated: {
            AppController.speechRecognitionModel = currentValue;
            root.inspector.scheduleSave();
        }
    }
    Text {
        Layout.fillWidth: true
        text: AppController.enableAudioSeparation
            ? qsTr("Nguồn nhận dạng: track giọng đã tách")
            : qsTr("Nguồn nhận dạng: âm thanh gốc")
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.metadata
        wrapMode: Text.Wrap
        textFormat: Text.PlainText
    }
    SettingLabel {
        Layout.fillWidth: true
        text: qsTr("Model dịch")
        helpText: qsTr("HY-MT2 chạy cục bộ. Gemini cần Internet và API key riêng; Google có thể tính phí theo mức sử dụng.")
    }
    TranslationModelCombo {
        Layout.fillWidth: true
        enabled: root.inspector.editable && !AppController.isProcessing
        selectedModel: AppController.translationModel
        onEdited: function(value) {
            AppController.translationModel = value;
            if (AppController.translationModel === value)
                root.inspector.scheduleSave();
        }
    }
    SettingLabel {
        Layout.fillWidth: true
        text: qsTr("Dịch sang")
    }
    SearchableLanguageCombo {
        Layout.fillWidth: true
        enabled: root.inspector.editable
        options: AppController.targetLanguageOptions
        selectedCode: AppController.targetLanguage
        onSelected: function(code) {
            AppController.targetLanguage = code;
            root.inspector.scheduleSave();
        }
    }
}
