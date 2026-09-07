import QtQuick
import QtQuick.Layouts
import "."

AppSurface {
    id: root

    padding: Theme.space16
    spacing: Theme.space8

    Text {
        Layout.fillWidth: true
        text: qsTr("Phát triển bởi")
        color: Theme.textSubtle
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.metadata
        font.weight: Font.DemiBold
        textFormat: Text.PlainText
    }

    Text {
        Layout.fillWidth: true
        text: "Mạch Hồng Hải"
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.section
        font.weight: Font.DemiBold
        textFormat: Text.PlainText
        elide: Text.ElideRight
    }

    Text {
        Layout.fillWidth: true
        text: qsTr("HaizFlow là dự án nguồn mở dành cho quy trình xử lý video cục bộ trên Windows.")
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.label
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        lineHeight: 1.3
        maximumLineCount: 2
        elide: Text.ElideRight
    }

    RowLayout {
        spacing: Theme.space16

        ExternalTextLink {
            text: "GitHub"
            destination: "https://github.com/MachHongHai/HaizFlow"
        }

        ExternalTextLink {
            text: "LinkedIn"
            destination: "https://www.linkedin.com/in/machhonghai/"
        }
    }
}
