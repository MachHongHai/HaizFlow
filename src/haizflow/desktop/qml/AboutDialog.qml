pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root

    title: qsTr("Giới thiệu")
    subtitle: "HaizFlow"
    preferredWidth: 650
    maximumWidth: 680
    maximumHeight: 800
    bodySpacing: Theme.space12

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space16

        Image {
            Layout.preferredWidth: 68
            Layout.preferredHeight: 68
            source: Qt.resolvedUrl("../assets/branding/haizflow-mark.png")
            sourceSize.width: 176
            sourceSize.height: 176
            fillMode: Image.PreserveAspectFit
            asynchronous: true
            Accessible.name: qsTr("Biểu tượng HaizFlow")
        }

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
                text: qsTr("Xử lý, dịch và lồng tiếng video trên Windows.")
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.body
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
            }

            Text {
                Layout.fillWidth: true
                text: qsTr("Miễn phí · Mã nguồn mở")
                color: Theme.textSubtle
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.label
                textFormat: Text.PlainText
            }
        }
    }

    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: 1
        color: Theme.divider
    }

    Text {
        Layout.fillWidth: true
        text: qsTr("Mình là Mạch Hồng Hải, nhà phát triển của HaizFlow. Nếu bạn thích ứng dụng này, đừng ngần ngại cho HaizFlow 1 sao trên Github")
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.control
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        lineHeight: 1.35
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: Theme.space4

        AboutLinkRow {
            label: qsTr("Trang web")
            value: "haizflow.pages.dev"
            destination: "https://haizflow.pages.dev/"
            copyValue: "https://haizflow.pages.dev/"
        }

        AboutLinkRow {
            label: qsTr("Mã nguồn")
            value: "MachHongHai/HaizFlow"
            destination: "https://github.com/MachHongHai/HaizFlow"
            copyValue: "https://github.com/MachHongHai/HaizFlow"
        }

        AboutLinkRow {
            label: qsTr("GitHub cá nhân")
            value: "github.com/MachHongHai"
            destination: "https://github.com/MachHongHai"
            copyValue: "https://github.com/MachHongHai"
        }

        AboutLinkRow {
            label: qsTr("Email")
            value: "machhonghaipr@gmail.com"
            copyValue: "machhonghaipr@gmail.com"
            linkEnabled: false
        }

        AboutLinkRow {
            label: "LinkedIn"
            value: "linkedin.com/in/machhonghai"
            destination: "https://www.linkedin.com/in/machhonghai/"
            copyValue: "https://www.linkedin.com/in/machhonghai/"
        }
    }

    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: 186
        radius: Theme.radius
        color: Theme.surfaceStrong
        border.width: 1
        border.color: Theme.outlineStrong

        RowLayout {
            anchors.fill: parent
            anchors.margins: Theme.space12
            spacing: Theme.space16

            Rectangle {
                Layout.preferredWidth: 160
                Layout.preferredHeight: 160
                radius: 6
                color: "white"
                clip: true

                Image {
                    id: donateQr
                    anchors.fill: parent
                    anchors.margins: 3
                    source: "https://img.vietqr.io/image/970415-109877870173-compact.png?addInfo=Donate+cho+HaizFlow&accountName=MACH+HONG+HAI"
                    sourceSize.width: 320
                    sourceSize.height: 320
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    Accessible.name: qsTr("Mã QR ủng hộ HaizFlow")
                }

                Text {
                    anchors.centerIn: parent
                    width: parent.width - Theme.space8
                    visible: donateQr.status === Image.Error
                    text: qsTr("Mở mã QR bằng liên kết bên cạnh")
                    color: "#17120D"
                    font.pixelSize: TypeScale.metadata
                    textFormat: Text.PlainText
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: Theme.space8

                Text {
                    Layout.fillWidth: true
                    text: qsTr("Ủng hộ HaizFlow")
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.section
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }

                Text {
                    Layout.fillWidth: true
                    text: qsTr("Nếu bạn muốn ủng hộ HaizFlow, đây là mã QR. Cảm ơn bạn rất nhiều! Chúc bạn một ngày tốt lành!")
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.label
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                }

                ExternalTextLink {
                    text: qsTr("Mở mã QR")
                    destination: "https://img.vietqr.io/image/970415-109877870173-compact.png?addInfo=Donate+cho+HaizFlow&accountName=MACH+HONG+HAI"
                }
            }
        }
    }

    footerActions: StudioButton {
        text: qsTr("Đóng")
        variant: "primary"
        onClicked: root.close()
    }
}
