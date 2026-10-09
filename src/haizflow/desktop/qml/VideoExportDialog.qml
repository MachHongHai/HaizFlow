pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root
    property var controller: AppController
    property var configuration: ({})
    property string destination: ""
    property bool destinationExists: false
    property bool processBeforeExport: false
    property bool batchMode: false
    title: batchMode ? qsTr("Xử lý và xuất hàng loạt") : processBeforeExport ? qsTr("Xử lý và xuất video") : qsTr("Xuất video")
    subtitle: processBeforeExport ? qsTr("Xử lý theo cài đặt dự án và lưu video vào vị trí đã chọn")
        : qsTr("Lưu bản sao thành phẩm; dữ liệu dự án được giữ nguyên")
    preferredWidth: 600
    bodySpacing: Theme.space12

    function openForSelection(processFirst = false) {
        batchMode = false;
        processBeforeExport = processFirst;
        configuration = controller.manualExportSettings();
        exportRange.currentIndex = 0;
        destination = "";
        destinationExists = false;
        quality.currentIndex = Math.max(0, (configuration.presets || []).findIndex(item => item.value === configuration.preset));
        open();
    }
    function openForProcessing() { openForSelection(true); }
    function openForBatch(processFirst = true) {
        openForSelection(processFirst);
        batchMode = true;
        configuration = controller.batchExportSettings();
        quality.currentIndex = Math.max(0, (configuration.presets || []).findIndex(item => item.value === configuration.preset));
    }
    RowLayout {
        Layout.fillWidth: true
        visible: !root.batchMode
        spacing: Theme.space12
        Text {
            text: qsTr("Tên tệp")
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.metadata
        }
        Text {
            Layout.fillWidth: true
            text: root.destination.length > 0
                ? root.destination.replace(/\\/g, "/").split("/").pop()
                : root.configuration.filename || ""
            textFormat: Text.PlainText
            elide: Text.ElideMiddle
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.control
            font.weight: Font.Medium
        }
    }
    FormSection {
        Layout.fillWidth: true
        visible: !root.batchMode && !root.processBeforeExport && (root.configuration.segments || []).length > 0
        title: qsTr("Phạm vi xuất")
        StudioComboBox {
            id: exportRange
            objectName: "exportRange"
            Layout.fillWidth: true
            textRole: "label"
            valueRole: "value"
            model: [{value: "", label: qsTr("Toàn bộ video")}].concat((root.configuration.segments || []).map(function(segment, index) {
                function time(ms) {
                    const seconds = Math.floor(ms / 1000);
                    return String(Math.floor(seconds / 60)).padStart(2, "0") + ":" + String(seconds % 60).padStart(2, "0")
                        + "." + String(ms % 1000).padStart(3, "0");
                }
                return {value: segment.id, label: qsTr("Đoạn %1 · %2 – %3").arg(index + 1).arg(time(segment.startMs)).arg(time(segment.endMs))};
            }))
        }
    }
    FormSection {
        Layout.fillWidth: true
        title: qsTr("Chất lượng video")
        StudioComboBox {
            id: quality
            objectName: "exportQuality"
            Layout.fillWidth: true
            model: root.configuration.presets || []
            textRole: "label"
            valueRole: "value"
        }
        Text {
            Layout.fillWidth: true
            text: qsTr("Giữ tỷ lệ khung hình, không tăng độ phân giải nguồn. Âm thanh giữ chất lượng bản phối.")
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.metadata
            wrapMode: Text.WordWrap
        }
        Text {
            Layout.fillWidth: true
            visible: root.batchMode
            text: qsTr("Áp dụng chất lượng xuất cho %1 video. Cài đặt xử lý riêng của từng video được giữ nguyên.").arg(root.configuration.count || 0)
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.pixelSize: TypeScale.metadata
            wrapMode: Text.WordWrap
        }
        Text {
            Layout.fillWidth: true
            visible: !root.processBeforeExport && !root.configuration.ready
            text: qsTr("Chưa có bản dựng phù hợp. HaizFlow sẽ dựng video từ các kết quả xử lý đã lưu trước khi xuất.")
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.metadata
            wrapMode: Text.WordWrap
        }
    }
    FormSection {
        Layout.fillWidth: true
        title: qsTr("Vị trí lưu")
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space8
            AppTextField {
                Layout.fillWidth: true
                readOnly: true
                text: root.destination
                placeholderText: qsTr("Chưa chọn vị trí lưu")
                accessibleName: qsTr("Đường dẫn xuất video")
            }
            StudioButton {
                text: qsTr("Chọn…")
                iconName: "folder"
                onClicked: {
                    const path = root.batchMode ? root.controller.chooseBatchExportDestination()
                        : root.controller.chooseVideoExportDestination(root.configuration.videoId);
                    if (path.length > 0) {
                        root.destination = path;
                        root.destinationExists = root.batchMode ? root.controller.batchExportDestinationExists(path)
                            : root.controller.exportDestinationExists(path);
                    }
                }
            }
        }
    }
    footerActions: [
        StudioButton { text: qsTr("Hủy"); variant: "ghost"; onClicked: root.close() },
        StudioButton {
            objectName: "confirmVideoExport"
            text: root.processBeforeExport ? qsTr("Xử lý và xuất") : qsTr("Xuất")
            variant: "primary"
            enabled: root.destination.length > 0 && !root.controller.videoExportBusy
            onClicked: {
                const started = root.batchMode
                    ? root.controller.processBatchTo(root.configuration.projectKey, root.configuration.videoIds,
                        quality.currentValue, root.destination, root.destinationExists, root.processBeforeExport)
                    : root.processBeforeExport
                    ? root.controller.processVideoTo(root.configuration.videoId, quality.currentValue, root.destination, root.destinationExists)
                    : exportRange.currentValue
                    ? root.controller.exportVideoSegmentTo(root.configuration.videoId, quality.currentValue, root.destination, root.destinationExists, exportRange.currentValue)
                    : root.controller.exportVideoTo(root.configuration.videoId, quality.currentValue, root.destination, root.destinationExists);
                if (started)
                    root.close();
            }
        }
    ]
}
