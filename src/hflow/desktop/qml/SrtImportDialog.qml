pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root
    property var controller: AppController
    property var selection: ({})
    property string videoId: ""
    title: qsTr("Nhập SRT")
    preferredWidth: 480

    function openForSelection() {
        videoId = String(controller.selectedVideoId || "");
        selection = ({});
        language.currentIndex = 0;
        open();
    }
    RowLayout {
        Layout.fillWidth: true
        AppTextField {
            Layout.fillWidth: true
            readOnly: true
            text: root.selection.filename || ""
            placeholderText: qsTr("Chọn tệp SRT")
        }
        StudioButton {
            objectName: "chooseSrtImport"
            text: qsTr("Chọn…")
            iconName: "folder"
            onClicked: {
                const result = root.controller.chooseSrtImportFile();
                if (!result.path || result.videoId !== root.videoId)
                    return;
                root.selection = result;
                language.currentIndex = Math.max(0, language.model.findIndex(item => item.value === result.language));
            }
        }
    }
    SettingLabel { Layout.fillWidth: true; text: qsTr("Ngôn ngữ SRT") }
    StudioComboBox {
        id: language
        objectName: "srtImportLanguage"
        Layout.fillWidth: true
        textRole: "label"
        valueRole: "value"
        model: [
            {value: "und", label: qsTr("Chọn ngôn ngữ · Khác")},
            {value: "vi", label: qsTr("Tiếng Việt")},
            {value: "en", label: qsTr("Tiếng Anh")},
            {value: "zh", label: qsTr("Tiếng Trung")}
        ]
    }
    footerActions: [
        StudioButton { text: qsTr("Hủy"); variant: "ghost"; onClicked: root.close() },
        DeferredActionButton {
            objectName: "confirmSrtImport"
            readyText: qsTr("Nhập")
            variant: "primary"
            actionEnabled: Boolean(root.selection.path) && !root.controller.isProcessing
                && !root.controller.videoExportBusy && !root.controller.mediaImportBusy
            actionContext: ({videoId: root.videoId, path: root.selection.path, language: language.currentValue})
            onExecute: context => {
                if (context.videoId === root.videoId
                        && root.controller.importSelectedSrt(context.path, context.language, context.videoId))
                    root.close();
            }
        }
    ]
}
