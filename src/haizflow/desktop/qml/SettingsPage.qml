pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

Item {
    id: root

    property string draftLanguage: ""
    property string draftDevice: ""
    property bool localEditsPending: false
    readonly property bool draftDirty: draftLanguage !== AppController.settingsLanguage || draftDevice !== AppController.processingDevice
    readonly property var hardwareInfo: AppController.hardwareInfo

    function loadDraft() {
        draftLanguage = AppController.settingsLanguage;
        draftDevice = AppController.processingDevice;
        localEditsPending = false;
    }

    function deviceStatus(device, hardwareSnapshot, interfaceLanguage) {
        // Both extra arguments are deliberate QML dependencies for the slot's
        // otherwise opaque hardware and localization reads.
        return AppController.processingDeviceStatus(device);
    }

    function applyDraft() {
        if (!localEditsPending || !draftDirty)
            return;
        if (AppController.applySettings("graphite", draftLanguage, draftDevice))
            loadDraft();
    }

    onVisibleChanged: {
        AppController.setHardwareTelemetryActive(visible);
        if (visible)
            loadDraft();
        else
            applyDraft();
    }

    Component.onCompleted: loadDraft()

    Connections {
        target: AppController
        function onSettingsChanged() {
            if (!root.localEditsPending)
                root.loadDraft();
        }
    }

    Timer {
        id: applyTimer
        interval: 250
        repeat: false
        onTriggered: root.applyDraft()
    }

    SettingsPageShell {
        anchors.fill: parent
        title: qsTr("Cài đặt")
        contentMaximumWidth: 920

        SettingRow {
                    Layout.fillWidth: true
                    Layout.topMargin: Theme.space16
                    Layout.bottomMargin: Theme.space16
                    label: qsTr("Ngôn ngữ giao diện")
                    description: qsTr("Áp dụng ngay, không cần khởi động lại.")
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
                            applyTimer.restart();
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
                    Layout.bottomMargin: Theme.space16
                    label: qsTr("Thiết bị xử lý")
                    description: root.deviceStatus(root.draftDevice, root.hardwareInfo, AppController.settingsLanguage)
                    SegmentedControl {
                        Layout.preferredWidth: 220
                        currentValue: root.draftDevice
                        options: [
                            {
                                label: qsTr("GPU"),
                                value: "gpu"
                            },
                            {
                                label: qsTr("CPU"),
                                value: "cpu"
                            }
                        ]
                        onActivated: function (value) {
                            root.draftDevice = value;
                            root.localEditsPending = true;
                            applyTimer.restart();
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
                    label: qsTr("Cấu hình đang dùng")
                    description: AppController.performanceProfileDetail
                }

                SettingRow {
                    Layout.fillWidth: true
                    Layout.bottomMargin: Theme.space16
                    label: qsTr("Giữ model sẵn sàng")
                    description: qsTr("Chuẩn bị model đã cài sau khi giao diện mở; tác vụ của bạn luôn được ưu tiên.")
                    AppSwitch {
                        text: ""
                        checked: AppController.keepModelsWarm
                        Accessible.name: qsTr("Giữ model sẵn sàng")
                        onToggled: AppController.setKeepModelsWarm(checked)
                    }
                }

                SettingRow {
                    Layout.fillWidth: true
                    Layout.bottomMargin: Theme.space12
                    label: qsTr("GPU")
                    description: root.hardwareInfo.activeGpuName || qsTr("Không khả dụng")
                }

                SettingRow {
                    Layout.fillWidth: true
                    Layout.bottomMargin: Theme.space16
                    label: qsTr("CPU")
                    description: root.hardwareInfo.cpuName || qsTr("Đang tải")
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
