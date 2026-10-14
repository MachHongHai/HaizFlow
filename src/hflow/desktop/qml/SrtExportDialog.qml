pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root
    property var controller: AppController
    property var configuration: ({})
    title: qsTr("Xuất SRT")
    preferredWidth: 440

    function openForSelection() {
        configuration = controller.srtExportSettings();
        if (!configuration.videoId)
            return;
        selection.currentIndex = configuration.result ? 0 : 1;
        open();
    }

    StudioComboBox {
        id: selection
        objectName: "srtExportKind"
        Layout.fillWidth: true
        textRole: "label"
        valueRole: "value"
        model: [
            {value: "result", label: qsTr("Phụ đề kết quả"), available: Boolean(root.configuration.result)},
            {value: "source", label: qsTr("Phụ đề ngôn ngữ gốc"), available: Boolean(root.configuration.source)},
            {value: "both", label: qsTr("Cả hai · 2 tệp SRT"), available: Boolean(root.configuration.result && root.configuration.source)}
        ]
    }
    footerActions: [
        StudioButton { text: qsTr("Hủy"); variant: "ghost"; onClicked: root.close() },
        StudioButton {
            objectName: "confirmSrtExport"
            text: qsTr("Xuất")
            variant: "primary"
            enabled: !root.controller.isProcessing && !root.controller.videoExportBusy && !root.controller.mediaImportBusy
                && (selection.currentValue === "source" ? root.configuration.source
                    : selection.currentValue === "both" ? root.configuration.source && root.configuration.result : root.configuration.result)
            onClicked: {
                if (root.controller.exportSelectedSrt(selection.currentValue, root.configuration.videoId))
                    root.close();
            }
        }
    ]
}
