pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

Item {
    id: root

    function packageTitle(packId, fallback) {
        switch (packId) {
        case "model-whisper-small": return qsTr("Whisper Small");
        case "model-whisper-turbo": return qsTr("Whisper Turbo");
        case "model-hymt2-cpu": return qsTr("HY-MT2 CPU");
        case "model-hymt2-gpu": return qsTr("HY-MT2 GPU");
        case "model-omnivoice": return qsTr("OmniVoice");
        default: return fallback;
        }
    }
    function packageGroupTitle(group) {
        if (group === "recognition") return qsTr("Nhận dạng");
        if (group === "translation") return qsTr("Dịch");
        return qsTr("Giọng đọc");
    }
    function packageSummary(packId, fallback) {
        switch (packId) {
        case "model-whisper-small": return qsTr("Nhận dạng lời nói bằng CPU hoặc GPU");
        case "model-whisper-turbo": return qsTr("Nhận dạng nhanh bằng GPU NVIDIA");
        case "model-hymt2-cpu": return qsTr("Dịch cục bộ bằng bản Q4");
        case "model-hymt2-gpu": return qsTr("Dịch bằng model đầy đủ trên GPU NVIDIA");
        case "model-omnivoice": return qsTr("Tạo giọng đọc cục bộ");
        default: return fallback;
        }
    }
    readonly property var packageRows: {
        // Re-evaluate when the selected device or package inventory changes.
        const device = AppController.processingDevice;
        const selectedVideo = AppController.selectedVideoId;
        const activity = AppController.resourcePackActivityText;
        const language = I18n.language;
        return AppController.resourcePackageRows;
    }
    ListModel {
        id: stableRows
        dynamicRoles: true
    }
    function syncPackageRows() {
        const rows = root.packageRows;
        let sameOrder = stableRows.count === rows.length;
        for (let i = 0; sameOrder && i < rows.length; ++i)
            sameOrder = stableRows.get(i).modelData.packId === rows[i].packId;
        if (!sameOrder) {
            stableRows.clear();
            for (let i = 0; i < rows.length; ++i)
                stableRows.append({modelData: rows[i]});
        } else {
            for (let i = 0; i < rows.length; ++i)
                stableRows.setProperty(i, "modelData", rows[i]);
        }
    }
    onPackageRowsChanged: root.syncPackageRows()
    Component.onCompleted: root.syncPackageRows()

    SettingsPageShell {
        anchors.fill: parent
        title: qsTr("Gói tài nguyên")
        showHeader: false
        contentMaximumWidth: 920
        pageInset: 0
        horizontalInset: 0
        alignLeft: false

        SettingRow {
                    Layout.fillWidth: true
                    Layout.topMargin: Theme.space16
                    Layout.bottomMargin: Theme.space16
                    label: qsTr("Cấu hình máy")
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
                        model: stableRows

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
                            groupFirst: Boolean(modelData.groupFirst)
                            groupTitle: root.packageGroupTitle(String(modelData.group || ""))
                        }
                    }
        }

        Item { Layout.preferredHeight: Theme.space24 }
        }
}
