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
    SettingLabel {
        Layout.fillWidth: true
        text: qsTr("Model nhận dạng")
        helpText: qsTr("Turbo cần GPU. Small dùng ít bộ nhớ hơn và hỗ trợ CPU.")
    }
    AppComboBox {
        Layout.fillWidth: true
        enabled: root.inspector.editable && !AppController.manualHasImportedSrt
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
        text: AppController.manualHasImportedSrt ? qsTr("Nguồn nhận dạng: SRT đã nhập") : AppController.enableAudioSeparation
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
        helpText: qsTr("HY-MT2 chạy cục bộ. Các model API cần Internet và key riêng; nhà cung cấp có thể tính phí.")
    }
    TranslationModelCombo {
        Layout.fillWidth: true
        enabled: root.inspector.editable && !AppController.isSwitchingProcessingDevice
        selectedModel: AppController.translationModel
        onEdited: function(value) {
            AppController.translationModel = value;
            if (AppController.translationModel === value)
                root.inspector.scheduleSave();
        }
    }
    TranslationReasoningControl {
        Layout.fillWidth: true
        enabled: root.inspector.editable
        selectedModel: AppController.translationModel
        reasoningEffort: AppController.translationReasoningEffort
        hasGuidance: Boolean(AppController.geminiTranslationInstructions || AppController.geminiTranslationGlossary
            || AppController.geminiTranslationStyle !== "balanced")
        onEdited: function(value) {
            AppController.translationReasoningEffort = value;
            root.inspector.scheduleSave();
        }
    }
    GeminiGuidanceButton {
        Layout.fillWidth: true
        visible: AppController.translationModel.indexOf("gemini-") === 0 || AppController.translationModel.indexOf("api:") === 0
        enabled: root.inspector.editable
        instructions: AppController.geminiTranslationInstructions
        glossary: AppController.geminiTranslationGlossary
        translationStyle: AppController.geminiTranslationStyle
        saveHandler: function(instructions, glossary, style, sourceKey) {
            return AppController.saveGeminiTranslationGuidance(AppController.projectKey,
                AppController.selectedVideoId, instructions, glossary, style, sourceKey);
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
