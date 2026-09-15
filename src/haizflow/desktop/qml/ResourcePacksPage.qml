pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

Item {
    id: root

    onVisibleChanged: AppController.setHardwareTelemetryActive(visible)
    Component.onCompleted: AppController.setHardwareTelemetryActive(visible)

    function packageTitle(packId, fallback) {
        switch (packId) {
        case "engine-cpu-py313": return qsTr("Bộ xử lý CPU");
        case "engine-cuda128-py313": return qsTr("Bộ xử lý NVIDIA");
        case "engine-vision-onnx": return qsTr("Bộ xử lý hình ảnh");
        case "model-speech-cpu": return qsTr("Nhận dạng và dịch · CPU");
        case "model-speech-gpu": return qsTr("Nhận dạng và dịch · NVIDIA");
        case "model-omnivoice": return qsTr("Giọng đọc OmniVoice");
        case "model-demucs": return qsTr("Tách giọng");
        case "model-subtitle-ocr": return qsTr("Che phụ đề gốc");
        default: return fallback;
        }
    }
    function packageGroupTitle(group) {
        if (group === "gpu")
            return AppController.hardwareInfo.recommendedDevice === "gpu"
                ? qsTr("NVIDIA · Khuyên dùng") : qsTr("NVIDIA");
        if (group === "cpu")
            return AppController.hardwareInfo.recommendedDevice === "cpu"
                ? qsTr("CPU · Khuyên dùng") : qsTr("CPU · Tùy chọn");
        return qsTr("Công cụ bổ sung");
    }
    readonly property var packageRows: {
        // Re-evaluate when the selected device or package inventory changes.
        const device = AppController.processingDevice;
        const selectedVideo = AppController.selectedVideoId;
        const activity = AppController.resourcePackActivityText;
        return AppController.resourcePackageRows;
    }

    SettingsPageShell {
        anchors.fill: parent
        title: qsTr("Gói cài đặt")
        contentMaximumWidth: 920

        SettingRow {
                    Layout.fillWidth: true
                    Layout.topMargin: Theme.space16
                    Layout.bottomMargin: Theme.space16
                    label: qsTr("Cấu hình phù hợp với máy này")
                    description: AppController.hardwareInfo.recommendedDevice === "gpu"
                        ? qsTr("NVIDIA · %1 · %2 VRAM")
                            .arg(AppController.hardwareInfo.availableGpuName)
                            .arg(AppController.hardwareInfo.totalVram)
                        : AppController.hardwareInfo.cpuName
                            ? qsTr("CPU · %1").arg(AppController.hardwareInfo.cpuName)
                            : qsTr("Đang đọc thông tin CPU…")
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    color: Theme.divider
                }

                SettingRow {
                    Layout.fillWidth: true
                    Layout.topMargin: Theme.space16
                    Layout.bottomMargin: Theme.space16
                    label: qsTr("Vị trí lưu")
                    description: qsTr("%1 · Đang dùng %2 · Còn trống %3")
                        .arg(AppController.resourcePackStorageLocation)
                        .arg(AppController.resourcePackInstalledText)
                        .arg(AppController.resourcePackFreeSpaceText)

                    StudioButton {
                        text: qsTr("Chuyển vị trí")
                        iconName: "folder"
                        variant: "secondary"
                        enabled: !AppController.resourcePackBusy
                        onClicked: AppController.browseAndMoveResourceStorage()
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    color: Theme.divider
                }

                ColumnLayout {
                    id: packageList
                    Layout.fillWidth: true
                    spacing: 0

                    Repeater {
                        id: packageRepeater
                        model: root.packageRows

                        delegate: ResourcePackRow {
                            Layout.fillWidth: true
                            required property var modelData
                            packId: String(modelData.packId || "")
                            label: root.packageTitle(String(modelData.packId || ""), String(modelData.label || ""))
                            version: String(modelData.version || "")
                            status: String(modelData.status || "missing")
                            progress: Number(modelData.progress ?? -1)
                            detail: String(modelData.detail || "")
                            summary: String(modelData.summary || "")
                            downloadSizeText: String(modelData.downloadSizeText || "")
                            installedSizeText: String(modelData.installedSizeText || "")
                            canInstall: Boolean(modelData.canInstall)
                            canRemove: Boolean(modelData.canRemove)
                            blockedReason: String(modelData.blockedReason || "")
                            hardwareCompatible: Boolean(modelData.hardwareCompatible)
                            hardwareWarning: String(modelData.hardwareWarning || "")
                            recommended: Boolean(modelData.recommended)
                            groupFirst: Boolean(modelData.groupFirst)
                            groupTitle: root.packageGroupTitle(String(modelData.group || ""))
                        }
                    }
        }

        Item { Layout.preferredHeight: Theme.space24 }
        }
}
