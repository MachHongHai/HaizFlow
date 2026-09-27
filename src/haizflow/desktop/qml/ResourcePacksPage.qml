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
        case "model-speech-cpu": return qsTr("Bộ ngôn ngữ · CPU");
        case "model-speech-gpu": return qsTr("Bộ ngôn ngữ · NVIDIA");
        case "model-omnivoice": return qsTr("Giọng đọc OmniVoice");
        case "model-demucs": return qsTr("Tách giọng");
        case "model-subtitle-ocr": return qsTr("Che phụ đề gốc");
        default: return fallback;
        }
    }
    function packageGroupTitle(group) {
        if (group === "runtime") return qsTr("Môi trường xử lý");
        if (group === "language") return qsTr("Nhận dạng và dịch");
        if (group === "audio") return qsTr("Giọng đọc và âm thanh");
        return qsTr("Hình ảnh và phụ đề gốc");
    }
    function packageSummary(packId, fallback) {
        switch (packId) {
        case "engine-cpu-py313": return qsTr("Môi trường chạy model bằng CPU");
        case "engine-cuda128-py313": return qsTr("Tăng tốc xử lý bằng GPU NVIDIA");
        case "model-speech-cpu": return qsTr("Whisper nhận dạng · HY-MT2 Q4 dịch · căn thời gian");
        case "model-speech-gpu": return qsTr("Whisper Small/Turbo nhận dạng · HY-MT2 dịch · căn thời gian");
        case "model-omnivoice": return qsTr("Tạo giọng đọc cục bộ");
        case "model-demucs": return qsTr("Tách giọng nói khỏi âm thanh nền");
        case "engine-vision-onnx": return qsTr("Môi trường xử lý hình ảnh");
        case "model-subtitle-ocr": return qsTr("Nhận dạng vị trí phụ đề gốc");
        default: return fallback;
        }
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
        title: qsTr("Gói tài nguyên")
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
                            summary: root.packageSummary(String(modelData.packId || ""), String(modelData.summary || ""))
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
