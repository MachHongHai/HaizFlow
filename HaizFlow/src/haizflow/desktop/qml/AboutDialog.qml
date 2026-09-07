pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root

    title: qsTr("Giới thiệu HaizFlow")
    subtitle: qsTr("Ứng dụng nguồn mở dành cho Windows")
    preferredWidth: 580
    maximumWidth: 620

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space16

        Image {
            Layout.preferredWidth: 88
            Layout.preferredHeight: 88
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
                text: qsTr("Công cụ xử lý và lồng tiếng video trên Windows.")
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.body
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
            }

            Text {
                Layout.fillWidth: true
                text: qsTr("Phát triển bởi Mạch Hồng Hải")
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
        text: qsTr("HaizFlow là phần mềm nguồn mở, ưu tiên xử lý video ngay trên máy và không yêu cầu dịch vụ API trả phí cho quy trình cốt lõi.")
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.control
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        lineHeight: 1.35
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
            toolTipText: qsTr("Sao chép liên kết")
            onClicked: AppController.copyText("https://github.com/MachHongHai/HaizFlow")
        }
    }

    SettingRow {
        Layout.fillWidth: true
        label: qsTr("Liên hệ")
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
            toolTipText: qsTr("Sao chép email")
            onClicked: AppController.copyText("machhonghaipr@gmail.com")
        }
    }

    SettingRow {
        Layout.fillWidth: true
        label: "LinkedIn"
        ExternalTextLink {
            text: "linkedin.com/in/machhonghai"
            destination: "https://www.linkedin.com/in/machhonghai/"
        }
        IconButton {
            controlSize: 28
            glyph: "\uE8C8"
            toolTipText: qsTr("Sao chép liên kết")
            onClicked: AppController.copyText("https://www.linkedin.com/in/machhonghai/")
        }
    }

    footerActions: StudioButton {
        text: qsTr("Đóng")
        variant: "primary"
        onClicked: root.close()
    }
}
