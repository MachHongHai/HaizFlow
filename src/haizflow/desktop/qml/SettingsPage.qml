pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import "."

Item {
    id: root
    property string draftLanguage: ""
    property string draftDevice: ""
    property bool draftKeepWarm: false
    property bool localEditsPending: false
    readonly property bool draftDirty: draftLanguage !== AppController.settingsLanguage
        || draftDevice !== AppController.processingDevice || draftKeepWarm !== AppController.keepModelsWarm

    function loadDraft() {
        draftLanguage = AppController.settingsLanguage;
        draftDevice = AppController.processingDevice;
        draftKeepWarm = AppController.keepModelsWarm;
        localEditsPending = false;
    }
    function applyDraft() {
        if (localEditsPending && draftDirty
            && AppController.applyGeneralSettings(draftLanguage, draftDevice, draftKeepWarm))
            loadDraft();
    }
    onVisibleChanged: { if (visible) loadDraft(); }
    Component.onCompleted: loadDraft()
    Connections {
        target: AppController
        function onSettingsChanged() { if (!root.localEditsPending) root.loadDraft(); }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.space16
        SettingsPageShell {
            Layout.fillWidth: true
            Layout.fillHeight: true
            showHeader: false
            pageInset: 0
            horizontalInset: 0
            alignLeft: false
            contentMaximumWidth: 920
            contentSpacing: Theme.space20
            SettingsGroup {
                Layout.fillWidth: true
                title: qsTr("Giao diện")
                SettingRow {
                    Layout.fillWidth: true
                    label: qsTr("Ngôn ngữ giao diện")
                    SegmentedControl {
                        objectName: "settingsLanguageChoice"
                        Layout.preferredWidth: 240
                        currentValue: root.draftLanguage
                        options: [{ label: qsTr("English"), value: "en" }, { label: qsTr("Tiếng Việt"), value: "vi" }]
                        onActivated: function(value) { root.draftLanguage = value; root.localEditsPending = true; }
                    }
                }
            }
            SettingsGroup {
                Layout.fillWidth: true
                title: qsTr("Xử lý")
                SettingRow {
                    Layout.fillWidth: true
                    label: qsTr("Bộ xử lý")
                    description: qsTr("Dùng cho nhận dạng, dịch và tạo giọng.")
                    SegmentedControl {
                        objectName: "settingsDeviceChoice"
                        Layout.preferredWidth: 240
                        currentValue: root.draftDevice
                        enabled: !AppController.isProcessing
                        options: [{ label: qsTr("CPU"), value: "cpu" }, { label: qsTr("GPU NVIDIA"), value: "gpu" }]
                        onActivated: function(value) { root.draftDevice = value; root.localEditsPending = true; }
                    }
                }
                SettingRow {
                    Layout.fillWidth: true
                    label: qsTr("Cấu hình đang dùng")
                    description: AppController.performanceProfileDetail
                }
                SettingRow {
                    Layout.fillWidth: true
                    label: qsTr("Giữ model sẵn sàng")
                    description: qsTr("Nạp trước Whisper khi mở ứng dụng. Tự giải phóng khi thiếu bộ nhớ.")
                    AppSwitch {
                        checked: root.draftKeepWarm
                        Accessible.name: qsTr("Giữ model sẵn sàng")
                        onToggled: { root.draftKeepWarm = checked; root.localEditsPending = true; }
                    }
                }
            }
            SettingsGroup {
                Layout.fillWidth: true
                title: qsTr("Ứng dụng")
                SettingRow {
                    Layout.fillWidth: true
                    label: qsTr("Cập nhật HaizFlow")
                    description: AppController.appUpdateState === "available"
                        ? qsTr("Phiên bản %1 đã sẵn sàng.").arg(AppController.latestAppVersion)
                        : AppController.appUpdateState === "checking" ? qsTr("Đang kiểm tra phiên bản mới…")
                        : qsTr("Phiên bản hiện tại: %1").arg(AppController.currentAppVersion)
                    StudioButton {
                        text: AppController.appUpdateState === "available" ? qsTr("Xem bản mới") : qsTr("Kiểm tra")
                        enabled: AppController.appUpdateState !== "checking"
                        onClicked: AppController.showAppUpdate()
                    }
                }
            }
            Item { Layout.preferredHeight: Theme.space8 }
        }
        ColumnLayout {
            objectName: "generalSettingsFooter"
            Layout.fillWidth: true
            Layout.maximumWidth: 920
            Layout.alignment: Qt.AlignHCenter
            spacing: Theme.space16
            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.divider }
            RowLayout {
                Layout.fillWidth: true
                Layout.bottomMargin: Theme.space8
                spacing: Theme.space8
                Item { Layout.fillWidth: true }
                StudioButton {
                    text: qsTr("Hủy thay đổi")
                    enabled: root.draftDirty
                    onClicked: root.loadDraft()
                }
                StudioButton {
                    objectName: "applyGeneralSettingsButton"
                    text: qsTr("Áp dụng")
                    variant: "primary"
                    enabled: root.draftDirty && !AppController.isProcessing
                    onClicked: root.applyDraft()
                }
            }
        }
    }
}
