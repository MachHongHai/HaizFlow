pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
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

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.space16

        SectionHeader {
            Layout.fillWidth: true
            title: qsTr("Cài đặt")
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.divider
        }

        ScrollView {
            id: settingsScroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            ScrollBar.vertical.policy: ScrollBar.AsNeeded

            ColumnLayout {
                width: Math.min(860, Math.max(1, settingsScroll.availableWidth - Theme.space24 * 2))
                x: Math.max(Theme.space24, Math.round((settingsScroll.availableWidth - width) / 2))
                spacing: 0

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
                    StatusBadge {
                        status: "success"
                        label: AppController.performanceProfileLabel
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
                    Layout.bottomMargin: Theme.space12
                    label: qsTr("Thư mục model")
                    description: AppController.modelSetupDirectory
                }

                InlineBanner {
                    Layout.fillWidth: true
                    tone: "info"
                    message: qsTr("Model và cache ứng dụng được lưu trong thư mục dữ liệu HaizFlow.")
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    Layout.topMargin: Theme.space16
                    color: Theme.divider
                }

                SettingRow {
                    Layout.fillWidth: true
                    Layout.topMargin: Theme.space16
                    Layout.bottomMargin: Theme.space16
                    label: qsTr("Xử lý cục bộ")
                    description: qsTr("Tệp video và kết quả model nằm trong thư mục dự án đã chọn.")
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
                    label: qsTr("Dữ liệu tạm của dự án thủ công")
                    description: qsTr("Xóa các bản dựng cũ; dữ liệu đang dùng được giữ lại.")
                    StudioButton {
                        text: qsTr("Dọn dữ liệu tạm")
                        iconName: "delete"
                        variant: "secondary"
                        onClicked: AppController.clearManualCache("all")
                    }
                }

            }
        }
    }
}
