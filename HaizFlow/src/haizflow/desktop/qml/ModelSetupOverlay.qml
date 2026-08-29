pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

FocusScope {
    id: root

    visible: AppController.modelSetupVisible
    enabled: visible
    focus: visible
    z: 1000

    Rectangle {
        anchors.fill: parent
        color: Theme.scrim
    }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        onClicked: root.forceActiveFocus()
    }

    AppSurface {
        anchors.centerIn: parent
        width: Math.min(parent.width - 48, 540)
        padding: Theme.space20
        spacing: Theme.space16

        SectionHeader {
            Layout.fillWidth: true
            title: AppController.modelSetupState === "failed"
                ? qsTr("Không tải được model")
                : AppController.modelSetupState === "cancelled"
                    ? qsTr("Đã tạm dừng tải model")
                    : qsTr("Đang tải model…")
            subtitle: qsTr("Model được lưu trong thư mục dữ liệu của ứng dụng.")
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space16

            Rectangle {
                Layout.preferredWidth: 36
                Layout.preferredHeight: 36
                radius: Theme.radiusSmall
                color: AppController.modelSetupState === "failed"
                    || AppController.modelSetupState === "cancelled"
                    ? Theme.dangerMuted : Theme.interactiveMuted

                AppIcon {
                    anchors.centerIn: parent
                    glyph: AppController.modelSetupState === "failed"
                        || AppController.modelSetupState === "cancelled"
                        ? "\uEA39" : "\uE896"
                    iconColor: AppController.modelSetupState === "failed"
                        || AppController.modelSetupState === "cancelled"
                        ? Theme.danger : Theme.interactive
                    iconSize: Theme.icon
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: Theme.space4

                Text {
                    Layout.fillWidth: true
                    text: AppController.modelSetupComponent.length > 0
                        ? AppController.modelSetupComponent
                        : qsTr("Gói model")
                    color: Theme.text
                    font.pixelSize: Theme.bodyLarge
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                }

                Text {
                    Layout.fillWidth: true
                    text: I18n.runtimeStatus(AppController.modelSetupDetail)
                    color: AppController.modelSetupState === "failed"
                        ? Theme.danger : Theme.textMuted
                    font.pixelSize: Theme.body
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            visible: AppController.modelSetupBusy
            spacing: Theme.space8

            RowLayout {
                Layout.fillWidth: true

                Text {
                    Layout.fillWidth: true
                    text: qsTr("Tiến trình tải")
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    textFormat: Text.PlainText
                }

                Text {
                    text: AppController.modelSetupProgress + "%"
                    color: Theme.text
                    font.pixelSize: Theme.caption
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }
            }

            AppProgressBar {
                Layout.fillWidth: true
                value: AppController.modelSetupProgress
            }

            Text {
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignRight
                text: AppController.modelSetupSizeText
                color: Theme.textSubtle
                font.pixelSize: Theme.label
                textFormat: Text.PlainText
            }
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: storageColumn.implicitHeight + Theme.space24
            radius: Theme.radiusSmall
            color: Theme.surfaceElevated
            border.width: 1
            border.color: Theme.outline

            ColumnLayout {
                id: storageColumn

                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: Theme.space16
                anchors.rightMargin: Theme.space16
                spacing: Theme.space4

                Text {
                    Layout.fillWidth: true
                    text: qsTr("Vị trí lưu model")
                    color: Theme.textMuted
                    font.pixelSize: Theme.label
                    textFormat: Text.PlainText
                }

                Text {
                    Layout.fillWidth: true
                    text: AppController.modelSetupDirectory
                    color: Theme.text
                    font.pixelSize: Theme.caption
                    textFormat: Text.PlainText
                    elide: Text.ElideMiddle
                }
            }
        }

        Text {
            Layout.fillWidth: true
            visible: AppController.modelSetupBusy
            text: qsTr("Giữ ứng dụng đang mở trong khi tải.")
            color: Theme.textSubtle
            font.pixelSize: Theme.caption
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
        }

        RowLayout {
            Layout.fillWidth: true
            visible: AppController.modelSetupState !== "ready"

            Item {
                Layout.fillWidth: true
            }

            AppButton {
                visible: AppController.modelSetupCanCancel
                text: qsTr("Tạm dừng tải")
                tone: "secondary"
                onClicked: AppController.cancelModelSetup()
            }

            AppButton {
                visible: !AppController.modelSetupBusy
                text: qsTr("Tải lại model")
                tone: "primary"
                iconGlyph: "\uE72C"
                onClicked: AppController.retryModelSetup()
            }
        }
    }

    Keys.onEscapePressed: function (event) {
        event.accepted = true
    }
}
