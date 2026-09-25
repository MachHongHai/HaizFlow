pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root

    property bool replacingVoice: false
    property string draftProvider: "omnivoice"
    property string draftVoice: ""
    property string draftSpeakerMode: "single"
    property string globalProvider: "omnivoice"
    property string globalVoice: ""
    property string openedVideoId: ""
    property string referencePathSnapshot: ""
    property var voiceModel: []

    signal confirmed(string provider, string voice, string scope, string segmentId, string speakerMode)
    signal cloneRequested()

    title: replacingVoice ? qsTr("Đổi hoặc tạo lại giọng") : qsTr("Tạo giọng đọc")
    preferredWidth: 560
    preferredHeight: 410
    maximumHeight: 680

    function providerIndex(value) {
        const options = AppController.ttsProviderOptions || [];
        for (let index = 0; index < options.length; ++index) {
            if (String(options[index].provider || "") === String(value || ""))
                return index;
        }
        return 0;
    }

    function firstAvailableVoice(options) {
        for (let index = 0; index < options.length; ++index) {
            if (options[index].available === undefined || options[index].available !== false)
                return String(options[index].voice || "");
        }
        return "";
    }

    function refreshVoices(preferredVoice) {
        voiceModel = AppController.manualVoiceOptionsForProvider(draftProvider);
        const requested = String(preferredVoice || "");
        for (let index = 0; index < voiceModel.length; ++index) {
            if (String(voiceModel[index].voice || "") === requested
                    && (voiceModel[index].available === undefined || voiceModel[index].available !== false)) {
                draftVoice = requested;
                return;
            }
        }
        draftVoice = firstAvailableVoice(voiceModel);
    }

    function openForVoice(hasVoice, configuration) {
        openedVideoId = String(AppController.selectedVideoId || "");
        referencePathSnapshot = String(AppController.voiceCloneReferencePath || "");
        replacingVoice = Boolean(hasVoice);
        globalProvider = String(configuration.globalProvider || configuration.provider || "omnivoice");
        globalVoice = String(configuration.globalVoice || configuration.voice || "");
        draftSpeakerMode = String(configuration.speakerMode || "single");
        draftProvider = globalProvider;
        refreshVoices(globalVoice);
        open();
    }

    onClosed: voicePicker.stopPreview()

    Connections {
        target: AppController

        function onSelectedVideoChanged() {
            if (!root.opened)
                return;
            if (String(AppController.selectedVideoId || "") !== root.openedVideoId) {
                root.close();
                return;
            }
            const currentReference = String(AppController.voiceCloneReferencePath || "");
            const referenceJustAdded = root.referencePathSnapshot.length === 0
                && currentReference.length > 0;
            root.referencePathSnapshot = currentReference;
            // selectedVideoChanged is also emitted by progress and cache
            // updates. Those unrelated events must not replace the voice the
            // user picked in this draft. Select Clone only for the one event
            // that actually adds the first reference sample.
            const preferred = referenceJustAdded ? "omnivoice:clone" : root.draftVoice;
            root.refreshVoices(preferred);
        }
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: Theme.space16

        GridLayout {
            Layout.fillWidth: true
            columns: 2
            columnSpacing: Theme.space12
            rowSpacing: Theme.space8

            SettingLabel { text: qsTr("Công cụ") }
            SettingLabel { text: qsTr("Giọng đọc") }

            AppComboBox {
                id: providerBox
                Layout.fillWidth: true
                textRole: "label"
                valueRole: "provider"
                model: AppController.ttsProviderOptions
                currentIndex: root.providerIndex(root.draftProvider)
                onActivated: function(index) {
                    const option = model[index];
                    if (!option)
                        return;
                    root.draftProvider = String(option.provider || "omnivoice");
                    if (root.draftProvider !== "omnivoice")
                        root.draftSpeakerMode = "single";
                    root.refreshVoices("");
                }
            }

            VoicePicker {
                id: voicePicker
                Layout.fillWidth: true
                model: root.voiceModel
                currentValue: root.draftVoice
                allowVoiceClone: true
                previewEnabled: true
                previewSource: AppController.audioPreviewSource
                previewState: AppController.audioPreviewState
                onSelected: function(voice) { root.draftVoice = voice; }
                onPreviewRequested: function(voice) {
                    AppController.previewVoiceSample(
                        root.draftProvider,
                        voice,
                        AppController.targetLanguage
                    );
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            visible: root.draftProvider === "omnivoice"
            spacing: Theme.space8

            AppCheckBox {
                Layout.fillWidth: true
                text: qsTr("Nhận diện nhiều người nói")
                checked: root.draftSpeakerMode === "multiple"
                onToggled: root.draftSpeakerMode = checked ? "multiple" : "single"
            }

            StudioButton {
                text: AppController.voiceCloneReferencePath.length > 0
                    ? qsTr("Đổi mẫu giọng") : qsTr("Thêm mẫu giọng")
                iconName: "volume"
                variant: "secondary"
                onClicked: root.cloneRequested()
            }
        }

    }

    footerActions: [
        StudioButton {
            text: qsTr("Hủy")
            variant: "secondary"
            onClicked: root.close()
        },
        StudioButton {
            text: qsTr("Tạo giọng")
            iconName: "play"
            variant: "primary"
            enabled: root.draftVoice.length > 0
            onClicked: {
                root.confirmed(
                    root.draftProvider,
                    root.draftVoice,
                    "all",
                    "",
                    root.draftSpeakerMode
                );
                root.close();
            }
        }
    ]
}
