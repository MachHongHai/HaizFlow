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
        case "model-vieneu": return qsTr("VieNeu CPU / GPU");
        case "model-demucs-cpu": return qsTr("Demucs CPU");
        case "model-demucs-gpu": return qsTr("Demucs GPU NVIDIA");
        case "model-subtitle-ocr": return qsTr("Nhận diện phụ đề gốc");
        case "browser-douyin-chromium": return qsTr("Trình duyệt Douyin (Chromium)");
        default: return fallback;
        }
    }
    function packageGroupTitle(group) {
        if (group === "recognition") return qsTr("Nhận dạng");
        if (group === "translation") return qsTr("Dịch");
        if (group === "separation") return qsTr("Tách giọng");
        if (group === "image") return qsTr("Hình ảnh");
        if (group === "downloads") return qsTr("Tải xuống");
        return qsTr("Giọng đọc");
    }
    function packageSummary(packId, fallback) {
        switch (packId) {
        case "model-whisper-small": return qsTr("Nhận dạng lời nói bằng CPU hoặc GPU");
        case "model-whisper-turbo": return qsTr("Nhận dạng nhanh bằng GPU NVIDIA");
        case "model-hymt2-cpu": return qsTr("Dịch cục bộ bằng bản Q4");
        case "model-hymt2-gpu": return qsTr("Dịch bằng model đầy đủ trên GPU NVIDIA");
        case "model-omnivoice": return qsTr("Tạo giọng đọc cục bộ");
        case "model-vieneu": return qsTr("25 giọng tiếng Việt · CPU hoặc GPU ít VRAM");
        case "model-demucs-cpu": return qsTr("Tách giọng nói khỏi nhạc trên CPU");
        case "model-demucs-gpu": return qsTr("Tách giọng nói khỏi nhạc trên GPU NVIDIA");
        case "model-subtitle-ocr": return qsTr("Nhận diện vị trí phụ đề gốc trong video");
        case "browser-douyin-chromium": return qsTr("Tạo phiên Douyin riêng. Tải từ nguồn Chromium chính thức, không dùng trình duyệt cá nhân.");
        default: return fallback;
        }
    }
    property var packageRows: []
    property bool inventoryDirty: true
    readonly property string inventoryContext: AppController.processingDevice + "|"
        + AppController.selectedVideoId + "|" + I18n.language
    onInventoryContextChanged: invalidateInventory()
    onVisibleChanged: if (visible && inventoryDirty) inventoryTimer.restart()
    function invalidateInventory() {
        inventoryDirty = true;
        if (visible) inventoryTimer.restart();
    }
    Timer {
        id: inventoryTimer
        interval: 40
        onTriggered: {
            if (!root.visible || !root.inventoryDirty) return;
            root.inventoryDirty = false;
            root.packageRows = AppController.resourcePackageRows;
        }
    }
    Connections { target: AppController; function onResourcePacksChanged() { root.invalidateInventory(); } }
    ListModel {
        id: stableRows
        dynamicRoles: true
    }
    function syncPackageRows() {
        const rows = root.packageRows;
        if (!rows) return;
        let sameOrder = stableRows.count === rows.length;
        for (let i = 0; sameOrder && i < rows.length; ++i)
            sameOrder = stableRows.get(i).modelData.packId === rows[i].packId;
        if (!sameOrder) {
            stableRows.clear();
            for (let i = 0; i < rows.length; ++i)
                stableRows.append({modelData: rows[i]});
        } else {
            for (let i = 0; i < rows.length; ++i)
                if (JSON.stringify(stableRows.get(i).modelData) !== JSON.stringify(rows[i]))
                    stableRows.setProperty(i, "modelData", rows[i]);
        }
    }
    onPackageRowsChanged: root.syncPackageRows()
    Component.onCompleted: root.invalidateInventory()

    SettingsPageShell {
        anchors.fill: parent
        title: qsTr("Gói tài nguyên")
        showHeader: false
        contentMaximumWidth: 920
        pageInset: 0
        horizontalInset: 0
        alignLeft: false
        contentSpacing: Theme.space20

        SettingsGroup {
            Layout.fillWidth: true
            title: qsTr("Bộ nhớ và thiết bị")
        SettingRow {
                    Layout.fillWidth: true
                    label: qsTr("Cấu hình máy")
                    description: AppController.hardwareInfo.recommendedDevice === "gpu"
                        ? qsTr("NVIDIA · %1 · %2 VRAM")
                            .arg(AppController.hardwareInfo.availableGpuName)
                            .arg(AppController.hardwareInfo.totalVram)
                        : AppController.hardwareInfo.cpuName
                            ? qsTr("CPU · %1").arg(AppController.hardwareInfo.cpuName)
                            : qsTr("Đang đọc thông tin CPU…")
                }

                SettingRow {
                    Layout.fillWidth: true
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

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.bottomMargin: Theme.space16
                    visible: AppController.resourcePackStorageMoving
                    spacing: Theme.space8
                    Text {
                        Layout.fillWidth: true
                        text: AppController.resourcePackActivityProgress < 0
                            ? AppController.resourcePackActivityText
                            : qsTr("%1 · %2%").arg(AppController.resourcePackActivityText)
                                .arg(Math.round(AppController.resourcePackActivityProgress))
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: TypeScale.metadata
                        textFormat: Text.PlainText
                    }
                    AppProgressBar {
                        Layout.fillWidth: true
                        value: Math.max(0, AppController.resourcePackActivityProgress)
                        indeterminate: AppController.resourcePackActivityProgress < 0
                        active: parent.visible
                    }
                }

        }
                SettingsGroup {
                    id: packageList
                    Layout.fillWidth: true
                    title: qsTr("Các gói tài nguyên")

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
