pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root
    spacing: 0

    RowLayout {
        Layout.fillWidth: true
        Layout.topMargin: Theme.space20
        Layout.bottomMargin: Theme.space8
        spacing: Theme.space12

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2

            Text {
                Layout.fillWidth: true
                text: qsTr("Gói tài nguyên")
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.title
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
            }

            Text {
                Layout.fillWidth: true
                text: qsTr("Đã dùng %1 · còn trống %2").arg(AppController.resourcePackInstalledText)
                    .arg(AppController.resourcePackFreeSpaceText)
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.label
                textFormat: Text.PlainText
            }
        }

        StudioButton {
            text: qsTr("Chuyển vị trí")
            iconName: "folder"
            variant: "secondary"
            enabled: !AppController.resourcePackBusy
            onClicked: AppController.browseAndMoveResourceStorage()
        }

        StudioButton {
            text: qsTr("Dọn gói không dùng")
            iconName: "delete"
            variant: "secondary"
            enabled: !AppController.resourcePackBusy
            onClicked: AppController.cleanUnusedResourcePacks()
        }
    }

    Text {
        Layout.fillWidth: true
        Layout.bottomMargin: Theme.space8
        text: AppController.resourcePackStorageLocation
        color: Theme.textSubtle
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.metadata
        elide: Text.ElideMiddle
        textFormat: Text.PlainText
    }

    Repeater {
        model: AppController.resourcePackModel

        delegate: ResourcePackRow {
            Layout.fillWidth: true
        }
    }
}
