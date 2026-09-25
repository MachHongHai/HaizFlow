pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

ColumnLayout {
    property var inspector
    spacing: Theme.space8
    SettingLabel {
        Layout.fillWidth: true
        text: qsTr("Model nhận dạng")
        helpText: qsTr("Turbo cần GPU. Small dùng ít bộ nhớ hơn và hỗ trợ CPU.")
    }
    AppComboBox {
        Layout.fillWidth: true
        enabled: inspector.editable
        textRole: "label"
        valueRole: "value"
        model: AppController.speechRecognitionModelOptions
        currentIndex: AppController.speechRecognitionModelIndex
        onActivated: {
            AppController.speechRecognitionModel = currentValue;
            inspector.scheduleSave();
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
        text: qsTr("Dịch sang")
    }
    SearchableLanguageCombo {
        Layout.fillWidth: true
        enabled: inspector.editable
        options: AppController.targetLanguageOptions
        selectedCode: AppController.targetLanguage
        onSelected: function(code) {
            AppController.targetLanguage = code;
            inspector.scheduleSave();
        }
    }
}

