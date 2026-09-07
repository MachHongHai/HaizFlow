import QtQuick
import QtQuick.Layouts
import "."

AppSurface {
    id: root

    padding: Theme.space12
    spacing: Theme.space12

    Text {
        Layout.fillWidth: true
        text: qsTr("Hướng dẫn sử dụng")
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.section
        font.weight: Font.DemiBold
        textFormat: Text.PlainText
    }

    Rectangle {
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.minimumHeight: 170
        radius: Theme.radiusSmall
        color: Theme.video
        border.width: 1
        border.color: Theme.outline

        Column {
            anchors.centerIn: parent
            width: Math.min(parent.width - Theme.space32, 220)
            spacing: Theme.space8

            FluentIcon {
                anchors.horizontalCenter: parent.horizontalCenter
                width: 28
                height: 28
                name: "video"
                iconColor: Theme.textDisabled
                iconSize: 26
            }

            Text {
                width: parent.width
                text: qsTr("Video hướng dẫn")
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.control
                font.weight: Font.DemiBold
                horizontalAlignment: Text.AlignHCenter
                textFormat: Text.PlainText
            }
        }
    }
}
