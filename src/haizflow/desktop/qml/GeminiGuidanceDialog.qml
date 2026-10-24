pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

AppDialog {
    id: root
    property string owner: ""
    property string translationStyle: "balanced"
    readonly property var styleOptions: [
        { label: qsTr("Cân bằng"), value: "balanced", description: qsTr("Rõ nghĩa, trung tính và dễ đọc.") },
        { label: qsTr("Sát nghĩa"), value: "literal", description: qsTr("Bám sát câu gốc, hạn chế diễn đạt lại.") },
        { label: qsTr("Tự nhiên"), value: "natural", description: qsTr("Ưu tiên lời thoại tự nhiên trong ngôn ngữ đích.") },
        { label: qsTr("Linh hoạt"), value: "adaptive", description: qsTr("Chuyển thành ngữ, hài hước và cảm xúc phù hợp; không thêm ý.") }
    ]
    signal confirmed(string instructions, string glossary, string owner, string style)
    title: qsTr("Văn phong và hướng dẫn dịch")
    preferredWidth: 640
    maximumHeight: 740
    bodySpacing: Theme.space8

    function openForGuidance(instructions, glossary, context, style) {
        owner = context;
        translationStyle = styleOptions.some(function(option) { return option.value === style; }) ? style : "balanced";
        instructionsEditor.text = instructions;
        glossaryEditor.text = glossary;
        open();
    }

    SettingLabel { text: qsTr("Văn phong dịch") }
    AppComboBox {
        id: styleCombo
        objectName: "geminiStyleCombo"
        Layout.fillWidth: true
        textRole: "label"
        valueRole: "value"
        model: root.styleOptions
        currentIndex: root.styleOptions.findIndex(function(option) { return option.value === root.translationStyle; })
        onActivated: root.translationStyle = currentValue
        Accessible.name: qsTr("Văn phong dịch")
    }
    Text {
        Layout.fillWidth: true
        text: root.styleOptions[Math.max(0, styleCombo.currentIndex)].description
        textFormat: Text.PlainText
        wrapMode: Text.Wrap
        color: Theme.textMuted
        font.pixelSize: TypeScale.metadata
    }
    SettingLabel { text: qsTr("Bối cảnh và cách dịch") }
    ScrollView {
        Layout.fillWidth: true
        Layout.minimumHeight: 64
        Layout.preferredHeight: 100
        contentWidth: availableWidth
        clip: true
        AppTextArea {
            id: instructionsEditor
            objectName: "geminiInstructionsEditor"
            accessibleName: qsTr("Bối cảnh và hướng dẫn dịch")
            placeholderText: qsTr("Ví dụ: Bối cảnh hiện đại. Dịch tự nhiên, ngắn gọn. Giữ nguyên sắc thái của từng nhân vật.")
        }
    }
    SettingLabel { text: qsTr("Tên nhân vật và xưng hô") }
    ScrollView {
        Layout.fillWidth: true
        Layout.minimumHeight: 72
        Layout.preferredHeight: 116
        contentWidth: availableWidth
        clip: true
        AppTextArea {
            id: glossaryEditor
            objectName: "geminiGlossaryEditor"
            accessibleName: qsTr("Quy ước tên nhân vật và xưng hô")
            placeholderText: qsTr("王明 → Vương Minh\nMinh và Lan là bạn cùng tuổi: tôi – cậu.\nLan nói với bố: con – bố.")
        }
    }
    Text {
        objectName: "geminiGuidanceDisclosure"
        Layout.fillWidth: true
        text: qsTr("Phụ đề và hướng dẫn được gửi tới Google khi dịch.")
        textFormat: Text.PlainText
        wrapMode: Text.Wrap
        color: Theme.textMuted
        font.pixelSize: TypeScale.metadata
    }
    Text {
        Layout.fillWidth: true
        visible: instructionsEditor.length > 4000 || glossaryEditor.length > 4000
        text: qsTr("Mỗi ô tối đa 4000 ký tự.")
        color: Theme.danger
        font.pixelSize: TypeScale.metadata
    }
    footerActions: [
        StudioButton { text: qsTr("Hủy"); variant: "secondary"; onClicked: root.close() },
        StudioButton {
            objectName: "saveGeminiGuidance"
            text: qsTr("Lưu")
            variant: "primary"
            enabled: instructionsEditor.length <= 4000 && glossaryEditor.length <= 4000
            onClicked: {
                root.confirmed(instructionsEditor.text.trim(), glossaryEditor.text.trim(), root.owner, root.translationStyle);
            }
        }
    ]
}
