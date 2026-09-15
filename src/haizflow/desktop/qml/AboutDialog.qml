pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root

    title: qsTr("Giới thiệu")
    subtitle: "HaizFlow"
    preferredWidth: 580
    maximumWidth: 620

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space16

        Image {
            Layout.preferredWidth: 80
            Layout.preferredHeight: 80
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
        text: qsTr("Các tính năng cốt lõi chạy trên máy của bạn. HaizFlow không yêu cầu API trả phí và không tự gửi tệp dự án lên máy chủ khác.")
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
            label: qsTr("Mã nguồn")
            value: "MachHongHai/HaizFlow"
            destination: "https://github.com/MachHongHai/HaizFlow"
            copyValue: "https://github.com/MachHongHai/HaizFlow"
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

    footerActions: StudioButton {
        text: qsTr("Đóng")
        variant: "primary"
        onClicked: root.close()
    }
}
