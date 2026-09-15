pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
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
    required property string summary
    required property string downloadSizeText
    required property string installedSizeText
    required property bool canInstall
    required property bool canRemove
    required property string blockedReason
    required property bool hardwareCompatible
    required property string hardwareWarning
    required property bool recommended
    required property bool groupFirst
    required property string groupTitle

    spacing: 0

    function statusLabel(value) {
        switch (value) {
        case "installed": return qsTr("Đã cài");
        case "bundled": return qsTr("Có sẵn");
        case "inventory": return qsTr("Đang kiểm tra");
        case "checking": return qsTr("Đang kiểm tra");
        case "downloading": return qsTr("Đang tải");
        case "verifying": return qsTr("Đang xác minh");
        case "removing": return qsTr("Đang gỡ");
        case "paused": return qsTr("Đã tạm dừng");
        case "failed": return qsTr("Lỗi");
        default: return qsTr("Chưa cài");
        }
    }

    SettingsSectionHeader {
        visible: root.groupFirst
        Layout.fillWidth: true
        Layout.topMargin: Theme.space20
        Layout.leftMargin: Theme.space4
        Layout.rightMargin: Theme.space4
        title: root.groupTitle
    }

    RowLayout {
        Layout.fillWidth: true
        Layout.minimumHeight: 78
        Layout.leftMargin: Theme.space4
        Layout.rightMargin: Theme.space4
        Layout.topMargin: Theme.space8
        Layout.bottomMargin: Theme.space8
        spacing: Theme.space12

        ColumnLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            spacing: 3

            Text {
                Layout.fillWidth: true
                text: root.label
                color: Theme.text
                font {
                    family: Theme.fontFamily
                    pixelSize: TypeScale.control
                    weight: Font.DemiBold
                }
                elide: Text.ElideRight
                textFormat: Text.PlainText
            }

            Text {
                Layout.fillWidth: true
                text: root.summary
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.metadata
                elide: Text.ElideRight
                textFormat: Text.PlainText
            }

            Text {
                Layout.fillWidth: true
                text: root.detail.length > 0 ? root.detail
                    : !root.hardwareCompatible ? root.hardwareWarning
                    : root.blockedReason.length > 0 ? root.blockedReason
                    : root.status === "bundled" ? qsTr("Có sẵn trong bản cài đặt")
                    : root.status === "installed" ? qsTr("Đã dùng %1").arg(root.installedSizeText)
                    : qsTr("Dung lượng tải %1").arg(root.downloadSizeText)
                color: root.status === "failed" || !root.hardwareCompatible
                    ? Theme.warning : Theme.textSubtle
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

        RowLayout {
            Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
            spacing: Theme.space8

            RowLayout {
                Layout.minimumWidth: 76
                Layout.alignment: Qt.AlignVCenter
                spacing: Theme.space4

                FluentIcon {
                    visible: root.status === "installed" || root.status === "bundled"
                    Layout.preferredWidth: 14
                    Layout.preferredHeight: 14
                    Layout.alignment: Qt.AlignVCenter
                    name: "check"
                    iconSize: 14
                    iconColor: Theme.success
                }

                Text {
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignVCenter
                    text: root.statusLabel(root.status)
                    color: root.status === "failed" ? Theme.danger : Theme.textMuted
                    font {
                        family: Theme.fontFamily
                        pixelSize: TypeScale.metadata
                        weight: root.status === "failed" ? Font.DemiBold : Font.Normal
                    }
                    horizontalAlignment: Text.AlignRight
                    verticalAlignment: Text.AlignVCenter
                    textFormat: Text.PlainText
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
                text: root.status === "paused" ? qsTr("Tiếp tục")
                    : root.status === "failed" ? qsTr("Thử lại") : qsTr("Cài đặt")
                iconName: "download"
                variant: "primary"
                enabled: root.canInstall
                onClicked: AppController.installResourcePacks([root.packId])
            }

            StudioIconButton {
                id: moreButton
                visible: root.status === "installed"
                iconName: "more"
                toolTipText: qsTr("Tùy chọn gói")
                onClicked: {
                    const point = moreButton.mapToItem(Overlay.overlay, 0, moreButton.height);
                    maintenanceMenu.x = Math.round(point.x - maintenanceMenu.width + moreButton.width);
                    maintenanceMenu.y = Math.round(point.y + Theme.space4);
                    maintenanceMenu.open();
                }
            }
        }
    }

    Rectangle {
        Layout.fillWidth: true
        Layout.leftMargin: Theme.space4
        Layout.preferredHeight: 1
        color: Theme.divider
    }

    TopBarPopupMenu {
        id: maintenanceMenu
        parent: Overlay.overlay
        menuContentWidth: Math.max(repairItem.implicitWidth, removeItem.implicitWidth)

        AppMenuItem {
            id: repairItem
            text: qsTr("Kiểm tra và sửa")
            iconGlyph: IconCatalog.glyph("refresh")
            onTriggered: AppController.repairResourcePack(root.packId)
        }

        AppMenuItem {
            id: removeItem
            text: qsTr("Gỡ gói")
            iconGlyph: IconCatalog.glyph("delete")
            tone: "danger"
            enabled: root.canRemove
            onTriggered: AppController.removeResourcePack(root.packId)
        }
    }
}
