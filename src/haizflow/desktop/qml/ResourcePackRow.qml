pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root

    required property string packId
    required property string label
    required property string version
    required property string status
    required property int progress
    required property string detail
    required property string downloadSizeText
    required property string installedSizeText
    required property bool canInstall
    required property bool canRemove
    required property string blockedReason
    required property bool groupFirst
    required property string groupTitle

    spacing: Theme.space8

    function statusLabel(value) {
        switch (value) {
        case "installed": return qsTr("Đã cài");
        case "bundled": return qsTr("Có sẵn");
        case "checking": return qsTr("Đang kiểm tra");
        case "downloading": return qsTr("Đang tải");
        case "verifying": return qsTr("Đang xác minh");
        case "paused": return qsTr("Đã tạm dừng");
        case "failed": return qsTr("Lỗi");
        default: return qsTr("Chưa cài");
        }
    }

    Text {
        visible: root.groupFirst
        Layout.fillWidth: true
        Layout.topMargin: Theme.space16
        text: root.groupTitle
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.section
        font.weight: Font.DemiBold
        textFormat: Text.PlainText
    }

    RowLayout {
        Layout.fillWidth: true
        Layout.minimumHeight: 54
        spacing: Theme.space12

        ColumnLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            spacing: 2

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space8

                Text {
                    Layout.fillWidth: true
                    text: root.label
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.control
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                    textFormat: Text.PlainText
                }

                StatusBadge {
                    status: root.status === "installed" || root.status === "bundled" ? "success"
                        : root.status === "failed" ? "error"
                        : root.status === "downloading" || root.status === "verifying" ? "processing"
                        : "ready"
                    label: root.statusLabel(root.status)
                }
            }

            Text {
                Layout.fillWidth: true
                text: root.detail.length > 0 ? root.detail
                    : root.blockedReason.length > 0 ? root.blockedReason
                    : root.status === "installed" || root.status === "bundled"
                        ? qsTr("Đã dùng %1 · phiên bản %2").arg(root.installedSizeText).arg(root.version)
                        : qsTr("Tải %1 · cài theo nhu cầu").arg(root.downloadSizeText)
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.metadata
                elide: Text.ElideRight
                textFormat: Text.PlainText
            }

            AppProgressBar {
                visible: root.progress >= 0 && ["checking", "downloading", "verifying"].indexOf(root.status) >= 0
                Layout.fillWidth: true
                Layout.topMargin: 2
                value: Math.max(0, root.progress)
            }
        }

        StudioButton {
            visible: root.status === "checking" || root.status === "downloading" || root.status === "verifying"
            text: qsTr("Tạm dừng")
            iconName: "pause"
            variant: "secondary"
            onClicked: AppController.cancelResourcePackOperation(root.packId)
        }

        StudioButton {
            visible: ["missing", "paused", "failed"].indexOf(root.status) >= 0
            text: root.status === "paused" ? qsTr("Tiếp tục") : qsTr("Cài đặt")
            iconName: "download"
            variant: "primary"
            enabled: root.canInstall
            onClicked: AppController.installResourcePacks([root.packId])
        }

        StudioButton {
            visible: root.status === "installed"
            text: qsTr("Sửa chữa")
            iconName: "refresh"
            variant: "secondary"
            onClicked: AppController.repairResourcePack(root.packId)
        }

        StudioButton {
            visible: root.status === "installed"
            text: qsTr("Gỡ bỏ")
            iconName: "delete"
            variant: "secondary"
            enabled: root.canRemove
            onClicked: AppController.removeResourcePack(root.packId)
        }
    }

    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: 1
        color: Theme.divider
    }
}
