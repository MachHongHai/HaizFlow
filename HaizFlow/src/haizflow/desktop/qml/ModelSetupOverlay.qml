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

    Panel {
        anchors.centerIn: parent
        width: Math.min(parent.width - 48, 620)
        contentPadding: 28
        contentSpacing: Theme.space20
        title: AppController.modelSetupState === "failed"
            ? I18n.t("Model setup needs attention")
            : AppController.modelSetupState === "cancelled"
                ? I18n.t("Model download paused")
                : I18n.t("Preparing HaizFlow")
        subtitle: I18n.t("Required AI models are downloaded once and stored beside the app in its runtime folder.")

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space16

            Rectangle {
                Layout.preferredWidth: 48
                Layout.preferredHeight: 48
                radius: 24
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
                    iconSize: Theme.iconLarge
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: Theme.space4

                Text {
                    Layout.fillWidth: true
                    text: AppController.modelSetupComponent.length > 0
                        ? AppController.modelSetupComponent
                        : I18n.t("AI model package")
                    color: Theme.text
                    font.pixelSize: Theme.bodyLarge
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                }

                Text {
                    Layout.fillWidth: true
                    text: I18n.t(AppController.modelSetupDetail)
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
                    text: I18n.t("Download progress")
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
                    text: I18n.t("Model storage location")
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
            text: I18n.t("Keep HaizFlow open and keep the internet connection active. Existing verified files will not be downloaded again.")
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
                text: I18n.t("Pause download")
                tone: "secondary"
                onClicked: AppController.cancelModelSetup()
            }

            AppButton {
                visible: !AppController.modelSetupBusy
                text: I18n.t("Retry model download")
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
