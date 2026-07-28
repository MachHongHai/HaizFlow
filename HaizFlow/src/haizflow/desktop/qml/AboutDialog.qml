import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Dialog {
    id: root

    modal: true
    focus: true
    width: Math.min(510, parent ? parent.width - 48 : 510)
    height: Math.min(490, parent ? parent.height - 48 : 490)
    padding: 0
    title: I18n.t("About HaizFlow")
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    parent: Overlay.overlay
    x: Math.round((parent.width - width) / 2)
    y: Math.round((parent.height - height) / 2)
    header: null
    footer: null

    background: Rectangle {
        radius: Theme.radius
        color: Theme.surface
        border.width: 1
        border.color: Theme.outlineStrong
    }

    contentItem: ColumnLayout {
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 64
            Layout.leftMargin: Theme.space24
            Layout.rightMargin: Theme.space16
            spacing: Theme.space12

            Text {
                Layout.fillWidth: true
                text: I18n.t("About HaizFlow")
                color: Theme.text
                font.pixelSize: Theme.h3
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
            }

            IconButton {
                glyph: "\uE711"
                toolTipText: I18n.t("Close")
                onClicked: root.close()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.divider
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: Theme.space24
            spacing: Theme.space16

            Image {
                Layout.alignment: Qt.AlignHCenter
                Layout.preferredWidth: 88
                Layout.preferredHeight: 88
                source: "../assets/branding/haizflow-mark.png"
                sourceSize: Qt.size(176, 176)
                asynchronous: true
                fillMode: Image.PreserveAspectFit
                Accessible.ignored: true
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: Theme.space4

                Text {
                    Layout.fillWidth: true
                    text: I18n.t("HaizFlow")
                    color: Theme.text
                    font.pixelSize: Theme.h2
                    font.weight: Font.DemiBold
                    horizontalAlignment: Text.AlignHCenter
                    textFormat: Text.PlainText
                }

                Text {
                    Layout.fillWidth: true
                    text: I18n.t("Local batch video reupload tool — no API fees")
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    textFormat: Text.PlainText
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: creatorContent.implicitHeight + Theme.space32
                radius: Theme.radiusSmall
                color: Theme.surfaceElevated
                border.width: 1
                border.color: Theme.outline

                ColumnLayout {
                    id: creatorContent

                    anchors.fill: parent
                    anchors.margins: Theme.space16
                    spacing: Theme.space8

                    Text {
                        Layout.fillWidth: true
                        text: I18n.t("Created by")
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                        textFormat: Text.PlainText
                    }

                    Text {
                        Layout.fillWidth: true
                        text: "Mạch Hồng Hải"
                        color: Theme.text
                        font.pixelSize: Theme.body
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                    }

                    Text {
                        Layout.fillWidth: true
                        text: I18n.t("Founder & Developer of HaizFlow")
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                        wrapMode: Text.Wrap
                        textFormat: Text.PlainText
                    }
                }
            }

            ColumnLayout {
                Layout.alignment: Qt.AlignHCenter
                spacing: Theme.space8

                RowLayout {
                    spacing: Theme.space8

                    Text {
                        text: I18n.t("GitHub") + ":"
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                        textFormat: Text.PlainText
                    }

                    ExternalTextLink {
                        text: "github.com/MachHongHai"
                        destination: "https://github.com/MachHongHai"
                    }

                    IconButton {
                        controlSize: 28
                        glyph: "\uE8C8"
                        toolTipText: I18n.t("Copy")
                        onClicked: AppController.copyText("https://github.com/MachHongHai")
                    }
                }

                RowLayout {
                    spacing: Theme.space8

                    Text {
                        text: I18n.t("Email") + ":"
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                        textFormat: Text.PlainText
                    }

                    Text {
                        text: "machhonghaipr@gmail.com"
                        color: Theme.interactive
                        font.pixelSize: Theme.caption
                        textFormat: Text.PlainText
                    }

                    IconButton {
                        controlSize: 28
                        glyph: "\uE8C8"
                        toolTipText: I18n.t("Copy")
                        onClicked: AppController.copyText("machhonghaipr@gmail.com")
                    }
                }
            }
        }
    }
}
