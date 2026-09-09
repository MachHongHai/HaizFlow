import QtQuick
import QtQuick.Layouts
import "."

GridLayout {
    id: root

    property bool editable: true
    property bool cpuOnly: false
    property bool hasSource: false
    property bool showCloneAction: false
    property bool cloneActive: false
    property string speechRecognitionModel: "small"
    property var speechRecognitionOptions: []
    property int speechRecognitionIndex: 0
    property string targetLanguage: "vi"
    property var targetLanguageOptions: []
    property string ttsProvider: "omnivoice"
    property var ttsProviderOptions: []
    property int ttsProviderIndex: 0
    property string ttsVoice: ""
    property var ttsVoiceOptions: []
    property string voicePreviewSource: ""
    property string voicePreviewState: "idle"
    property string speakerMode: "single"
    property bool removeOriginalSubtitles: true
    property string subtitleRemovalMode: "patch"
    property bool enableAudioSeparation: true
    property string backgroundMusicPath: ""
    property string watermarkText: ""

    signal speechRecognitionEdited(string value)
    signal targetLanguageEdited(string value)
    signal ttsProviderEdited(string value)
    signal ttsVoiceEdited(string value)
    signal ttsVoicePreviewRequested(string value)
    signal cloneVoiceRequested()
    signal speakerModeEdited(string value)
    signal removeOriginalSubtitlesEdited(bool value)
    signal subtitleRemovalModeEdited(string value)
    signal subtitleLayoutRequested()
    signal audioSeparationEdited(bool value)
    signal audioMixRequested()
    signal backgroundMusicFileRequested()
    signal backgroundMusicLinkRequested()
    signal backgroundMusicClearRequested()
    signal watermarkRequested()

    columns: width >= 760 ? 2 : 1
    columnSpacing: Theme.space20
    rowSpacing: Theme.space16

    Item {
        Layout.fillWidth: true
        Layout.fillHeight: root.columns === 2
        Layout.alignment: Qt.AlignTop
        implicitHeight: voiceColumn.implicitHeight

        ColumnLayout {
            id: voiceColumn
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.leftMargin: Theme.space4
            anchors.rightMargin: Theme.space4
            spacing: Theme.space8

            Text {
                text: qsTr("Ngôn ngữ và giọng")
                color: Theme.text
                font.pixelSize: Theme.body
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
            }

            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.divider }

            SettingLabel {
                Layout.fillWidth: true
                text: qsTr("Nhận dạng giọng nói")
                helpText: qsTr("Turbo cho chất lượng cao hơn trên GPU. Small dùng ít bộ nhớ hơn và hỗ trợ cả CPU.")
            }
            StudioComboBox {
                Layout.fillWidth: true
                enabled: root.editable
                textRole: "label"
                valueRole: "value"
                model: root.speechRecognitionOptions
                currentIndex: root.speechRecognitionIndex
                onActivated: root.speechRecognitionEdited(currentValue)
            }

            SettingLabel {
                Layout.fillWidth: true
                text: qsTr("Dịch sang")
            }
            SearchableLanguageCombo {
                Layout.fillWidth: true
                Layout.preferredHeight: 42
                enabled: root.editable
                options: root.targetLanguageOptions
                selectedCode: root.targetLanguage
                onSelected: function(code) { root.targetLanguageEdited(code) }
            }

            SettingLabel {
                Layout.fillWidth: true
                text: qsTr("Công cụ giọng đọc")
                helpText: qsTr("OmniVoice chạy cục bộ. Edge TTS cần kết nối Internet ổn định.")
            }
            StudioComboBox {
                Layout.fillWidth: true
                enabled: root.editable
                textRole: "label"
                valueRole: "provider"
                model: root.ttsProviderOptions
                currentIndex: root.ttsProviderIndex
                onActivated: root.ttsProviderEdited(currentValue)
            }

            SettingLabel {
                Layout.fillWidth: true
                text: qsTr("Giọng đọc")
            }
            VoicePicker {
                Layout.fillWidth: true
                enabled: root.editable
                model: root.ttsVoiceOptions
                currentValue: root.ttsVoice
                allowVoiceClone: false
                previewSource: root.voicePreviewSource
                previewState: root.voicePreviewState
                onSelected: function(voice) { root.ttsVoiceEdited(voice) }
                onPreviewRequested: function(voice) { root.ttsVoicePreviewRequested(voice) }
            }
            StudioButton {
                Layout.fillWidth: true
                visible: root.showCloneAction
                text: root.cloneActive ? qsTr("Giọng đã nhân bản") : qsTr("Nhân bản giọng")
                iconGlyph: "\uE77B"
                variant: root.cloneActive ? "primary" : "secondary"
                compact: true
                enabled: root.editable
                onClicked: root.cloneVoiceRequested()
            }

            RowLayout {
                Layout.fillWidth: true
                visible: root.ttsProvider === "omnivoice"
                StudioCheckBox {
                    Layout.fillWidth: true
                    enabled: root.editable && root.ttsProvider === "omnivoice"
                    text: qsTr("Nhận diện nhiều người nói")
                    checked: root.speakerMode === "multiple"
                    onToggled: root.speakerModeEdited(checked ? "multiple" : "single")
                }
                SettingLabel {
                    labelVisible: false
                    text: qsTr("Nhận diện nhiều người nói")
                    helpText: qsTr("Chỉ bật khi video nguồn có nhiều người nói. Mỗi người được nhận diện sẽ dùng một giọng riêng.")
                }
            }
        }
    }

    Item {
        Layout.fillWidth: true
        Layout.fillHeight: root.columns === 2
        Layout.alignment: Qt.AlignTop
        implicitHeight: mediaColumn.implicitHeight

        ColumnLayout {
            id: mediaColumn
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.leftMargin: Theme.space4
            anchors.rightMargin: Theme.space4
            spacing: Theme.space8

            Text {
                text: qsTr("Hình ảnh và âm thanh")
                color: Theme.text
                font.pixelSize: Theme.body
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
            }

            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.divider }

            SettingLabel {
                Layout.fillWidth: true
                text: qsTr("Phụ đề gốc")
            }
            SegmentedControl {
                Layout.fillWidth: true
                Layout.preferredHeight: 38
                enabled: root.editable
                currentValue: root.removeOriginalSubtitles ? "remove" : "keep"
                options: [
                    { "label": qsTr("Che phụ đề gốc"), "value": "remove" },
                    { "label": qsTr("Giữ nguyên video gốc"), "value": "keep" }
                ]
                onActivated: function(value) { root.removeOriginalSubtitlesEdited(value === "remove") }
            }

            SettingLabel {
                Layout.fillWidth: true
                visible: root.removeOriginalSubtitles
                text: qsTr("Cách xóa")
                helpText: qsTr("Làm mờ làm nhòe chữ được nhận diện. Vá nền dùng vùng ảnh sạch lân cận để lấp chữ.")
            }
            SegmentedControl {
                Layout.fillWidth: true
                Layout.preferredHeight: 38
                visible: root.removeOriginalSubtitles
                enabled: root.editable
                currentValue: root.subtitleRemovalMode
                options: [
                    { "label": qsTr("Làm mờ"), "value": "blur" },
                    { "label": qsTr("Vá nền lân cận"), "value": "patch" }
                ]
                onActivated: function(value) { root.subtitleRemovalModeEdited(value) }
            }

            StudioButton {
                Layout.alignment: Qt.AlignRight
                text: qsTr("Chỉnh phụ đề")
                compact: true
                variant: "secondary"
                enabled: root.editable && root.hasSource
                onClicked: root.subtitleLayoutRequested()
            }

            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.divider }

            SettingLabel {
                Layout.fillWidth: true
                text: qsTr("Nguồn âm thanh")
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space8
                SegmentedControl {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 38
                    enabled: root.editable
                    currentValue: root.enableAudioSeparation ? "separated" : "original"
                    options: [
                        { "label": qsTr("Giữ âm thanh gốc"), "value": "original" },
                        { "label": qsTr("Tách giọng"), "value": "separated" }
                    ]
                    onActivated: function(value) { root.audioSeparationEdited(value === "separated") }
                }
                StudioButton {
                    text: qsTr("Âm lượng")
                    variant: "secondary"
                    compact: true
                    enabled: root.editable
                    onClicked: root.audioMixRequested()
                }
            }
            Text {
                Layout.fillWidth: true
                visible: root.cpuOnly && root.enableAudioSeparation
                text: qsTr("Tách âm sẽ chậm hơn khi chạy bằng CPU")
                color: Theme.warning
                font.pixelSize: Theme.label
                wrapMode: Text.WordWrap
            }

            SettingLabel {
                Layout.fillWidth: true
                text: qsTr("Nhạc nền")
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space8
                Text {
                    Layout.fillWidth: true
                    text: root.backgroundMusicPath.length > 0 ? root.backgroundMusicPath : qsTr("Chưa có nhạc nền")
                    color: root.backgroundMusicPath.length > 0 ? Theme.text : Theme.textMuted
                    font.pixelSize: Theme.label
                    elide: Text.ElideMiddle
                }
                StudioButton { text: qsTr("Tệp"); enabled: root.editable; onClicked: root.backgroundMusicFileRequested() }
                StudioButton { text: qsTr("Liên kết"); enabled: root.editable; onClicked: root.backgroundMusicLinkRequested() }
                StudioIconButton {
                    visible: root.backgroundMusicPath.length > 0
                    iconName: "delete"
                    toolTipText: qsTr("Bỏ nhạc nền")
                    enabled: root.editable
                    onClicked: root.backgroundMusicClearRequested()
                }
            }

            SettingLabel {
                Layout.fillWidth: true
                text: qsTr("Watermark")
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space8
                Text {
                    Layout.fillWidth: true
                    text: root.watermarkText.length > 0 ? root.watermarkText : qsTr("Không có watermark")
                    color: root.watermarkText.length > 0 ? Theme.text : Theme.textMuted
                    font.pixelSize: Theme.label
                    elide: Text.ElideRight
                }
                StudioButton {
                    text: root.watermarkText.length > 0 ? qsTr("Chỉnh sửa") : qsTr("Thêm")
                    compact: true
                    enabled: root.editable
                    onClicked: root.watermarkRequested()
                }
            }
        }
    }
}
