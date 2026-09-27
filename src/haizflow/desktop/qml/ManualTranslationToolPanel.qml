pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root
    property var inspector
    spacing: Theme.space8
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
        helpText: qsTr("Áp dụng cho tất cả dự án. Q4 dùng ít bộ nhớ hơn.")
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
