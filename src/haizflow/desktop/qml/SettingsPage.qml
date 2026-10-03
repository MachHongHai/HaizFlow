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
        if (!localEditsPending || !draftDirty)
            return;
        if (AppController.applyGeneralSettings(draftLanguage, draftDevice, draftKeepWarm))
            loadDraft();
    }

    onVisibleChanged: {
        if (visible)
            loadDraft();
    }

    Component.onCompleted: loadDraft()

    Connections {
        target: AppController
        function onSettingsChanged() {
            if (!root.localEditsPending)
                root.loadDraft();
        }
    }

    SettingsPageShell {
        anchors.fill: parent
        title: qsTr("Cài đặt")
        showHeader: false
        contentMaximumWidth: 920

        SettingRow {
                    Layout.fillWidth: true
                    Layout.topMargin: Theme.space16
                    Layout.bottomMargin: Theme.space16
                    label: qsTr("Ngôn ngữ giao diện")
                    description: ""
                    SegmentedControl {
                        Layout.preferredWidth: 240
                        currentValue: root.draftLanguage
                        options: [
                            {
                                label: qsTr("English"),
                                value: "en"
                            },
                            {
                                label: qsTr("Tiếng Việt"),
                                value: "vi"
                            }
                        ]
                        onActivated: function (value) {
                            root.draftLanguage = value;
                            root.localEditsPending = true;
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    color: Theme.divider
                }

                SettingRow {
                    Layout.fillWidth: true
                    Layout.topMargin: Theme.space16
                    Layout.bottomMargin: Theme.space12
                    label: qsTr("Bộ xử lý")
                    description: qsTr("GPU NVIDIA yêu cầu bộ xử lý và gói tài nguyên tương thích.")
                    SegmentedControl {
                        Layout.preferredWidth: 240
                        currentValue: root.draftDevice
                        enabled: !AppController.isProcessing
                        options: [
                            { label: qsTr("CPU"), value: "cpu" },
                            { label: qsTr("GPU NVIDIA"), value: "gpu" }
                        ]
                        onActivated: function(value) { root.draftDevice = value; root.localEditsPending = true; }
                    }
                }

                SettingRow {
                    Layout.fillWidth: true
                    Layout.topMargin: Theme.space8
                    Layout.bottomMargin: Theme.space12
                    label: qsTr("Cấu hình đang dùng")
                    description: AppController.performanceProfileDetail
                }

                SettingRow {
                    Layout.fillWidth: true
                    Layout.bottomMargin: Theme.space16
                    label: qsTr("Giữ model sẵn sàng")
                    description: qsTr("Nạp trước Whisper khi mở ứng dụng. Tự giải phóng khi thiếu bộ nhớ.")
                    AppSwitch {
                        text: ""
                        checked: root.draftKeepWarm
                        Accessible.name: qsTr("Giữ model sẵn sàng")
                        onToggled: { root.draftKeepWarm = checked; root.localEditsPending = true; }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.bottomMargin: Theme.space16
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

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    color: Theme.divider
                }

                SettingRow {
                    Layout.fillWidth: true
                    Layout.topMargin: Theme.space16
                    Layout.bottomMargin: Theme.space16
                    label: qsTr("Cập nhật HaizFlow")
                    description: AppController.appUpdateState === "available"
                        ? qsTr("Phiên bản %1 đã sẵn sàng.").arg(AppController.latestAppVersion)
                        : AppController.appUpdateState === "checking"
                            ? qsTr("Đang kiểm tra phiên bản mới…")
                            : qsTr("Phiên bản hiện tại: %1").arg(AppController.currentAppVersion)

                    StudioButton {
                        text: AppController.appUpdateState === "available"
                            ? qsTr("Xem bản mới") : qsTr("Kiểm tra")
                        iconName: AppController.appUpdateState === "available" ? "open" : "refresh"
                        variant: AppController.appUpdateState === "available" ? "primary" : "secondary"
                        enabled: AppController.appUpdateState !== "checking"
                        onClicked: AppController.showAppUpdate()
                    }
        }
    }

}
