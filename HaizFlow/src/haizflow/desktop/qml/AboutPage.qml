pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.space16

        SectionHeader {
            Layout.fillWidth: true
            title: qsTr("Giới thiệu")
        }

        ScrollView {
            id: aboutScroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            ScrollBar.vertical.policy: ScrollBar.AsNeeded

            ColumnLayout {
                width: Math.min(920, Math.max(1, aboutScroll.availableWidth))
                x: Math.max(0, Math.round((aboutScroll.availableWidth - width) / 2))
                spacing: Theme.space16

                AppSurface {
                    Layout.fillWidth: true
                    padding: Theme.space24
                    spacing: Theme.space20

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 0

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: Theme.space4

                            Text {
                                Layout.fillWidth: true
                                text: "HaizFlow"
                                color: Theme.text
                                font.family: Theme.fontFamily
                                font.pixelSize: TypeScale.title
                                font.weight: Font.DemiBold
                                textFormat: Text.PlainText
                            }

                            Text {
                                Layout.fillWidth: true
                                text: qsTr("Xử lý, lồng tiếng và đăng video trên Windows.")
                                color: Theme.textMuted
                                font.family: Theme.fontFamily
                                font.pixelSize: TypeScale.body
                                textFormat: Text.PlainText
                                wrapMode: Text.WordWrap
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
                        label: qsTr("Phát triển")
                        description: "Mạch Hồng Hải"
                    }

                    SettingRow {
                        Layout.fillWidth: true
                        label: qsTr("Mã nguồn")
                        ExternalTextLink {
                            text: "MachHongHai/HaizFlow"
                            destination: "https://github.com/MachHongHai/HaizFlow"
                        }
                        IconButton {
                            controlSize: 28
                            glyph: "\uE8C8"
                            toolTipText: qsTr("Sao chép")
                            onClicked: AppController.copyText("https://github.com/MachHongHai/HaizFlow")
                        }
                    }

                    SettingRow {
                        Layout.fillWidth: true
                        label: qsTr("GitHub")
                        ExternalTextLink {
                            text: "github.com/MachHongHai"
                            destination: "https://github.com/MachHongHai"
                        }
                        IconButton {
                            controlSize: 28
                            glyph: "\uE8C8"
                            toolTipText: qsTr("Sao chép")
                            onClicked: AppController.copyText("https://github.com/MachHongHai")
                        }
                    }

                    SettingRow {
                        Layout.fillWidth: true
                        label: qsTr("Email")
                        Text {
                            Layout.fillWidth: true
                            text: "machhonghaipr@gmail.com"
                            color: Theme.textMuted
                            font.family: Theme.fontFamily
                            font.pixelSize: TypeScale.control
                            textFormat: Text.PlainText
                            elide: Text.ElideRight
                        }
                        IconButton {
                            controlSize: 28
                            glyph: "\uE8C8"
                            toolTipText: qsTr("Sao chép")
                            onClicked: AppController.copyText("machhonghaipr@gmail.com")
                        }
                    }
                }

                Text {
                    Layout.fillWidth: true
                    text: qsTr("Dữ liệu được xử lý trên máy, trừ các dịch vụ trực tuyến bạn chọn.")
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.label
                    horizontalAlignment: Text.AlignHCenter
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                }
            }
        }
    }
}
