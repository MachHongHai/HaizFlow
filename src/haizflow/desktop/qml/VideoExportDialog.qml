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
    title: qsTr("Xuất video")
    subtitle: qsTr("Lưu bản sao thành phẩm; dữ liệu dự án được giữ nguyên")
    preferredWidth: 600

    function openForSelection() {
        configuration = controller.manualExportSettings();
        destination = "";
        destinationExists = false;
        replaceCheck.checked = false;
        quality.currentIndex = Math.max(0, (configuration.presets || []).findIndex(item => item.value === configuration.preset));
        open();
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
            visible: !root.configuration.ready
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
        StudioButton {
            Layout.fillWidth: true
            text: root.destination.length > 0 ? qsTr("Chọn vị trí khác") : qsTr("Chọn vị trí và tên tệp")
            iconName: "folder"
            onClicked: {
                const path = root.controller.chooseVideoExportDestination(root.configuration.videoId);
                if (path.length > 0) {
                    root.destination = path;
                    root.destinationExists = root.controller.exportDestinationExists(path);
                    replaceCheck.checked = false;
                }
            }
        }
        Text {
            Layout.fillWidth: true
            visible: root.destination.length > 0
            text: root.destination
            textFormat: Text.PlainText
            wrapMode: Text.WrapAnywhere
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.metadata
        }
        AppCheckBox {
            id: replaceCheck
            Layout.fillWidth: true
            visible: root.destinationExists
            text: qsTr("Thay thế tệp đang có tại vị trí này")
        }
    }
    footerActions: [
        StudioButton { text: qsTr("Hủy"); variant: "ghost"; onClicked: root.close() },
        StudioButton {
            objectName: "confirmVideoExport"
            text: qsTr("Xuất")
            variant: "primary"
            enabled: root.destination.length > 0 && (!root.destinationExists || replaceCheck.checked) && !root.controller.videoExportBusy
            onClicked: {
                if (root.controller.exportVideoTo(root.configuration.videoId, quality.currentValue, root.destination, replaceCheck.checked))
                    root.close();
            }
        }
    ]
}
