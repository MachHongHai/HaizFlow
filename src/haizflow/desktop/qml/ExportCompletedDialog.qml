pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root

    property string outputPath: ""
    readonly property string outputName: {
        const normalized = outputPath.replace(/\\/g, "/");
        const parts = normalized.split("/");
        return parts.length > 0 && parts[parts.length - 1].length > 0
            ? parts[parts.length - 1] : qsTr("Video đã xuất");
    }

    signal openVideoRequested()
    signal openFolderRequested()

    title: qsTr("Video đã xuất")
    preferredWidth: 540
    maximumWidth: 600

    function showForOutput(path) {
        outputPath = String(path || "");
        open();
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space12

        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.space4

            Text {
                Layout.fillWidth: true
                text: root.outputName
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.body
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
                elide: Text.ElideMiddle
            }

            Text {
                Layout.fillWidth: true
                text: root.outputPath
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.metadata
                textFormat: Text.PlainText
                elide: Text.ElideMiddle
            }
        }
    }

    footerActions: [
        StudioButton {
            text: qsTr("Đóng")
            variant: "ghost"
            onClicked: root.close()
        },
        StudioButton {
            text: qsTr("Mở thư mục")
            iconName: "folder"
            variant: "secondary"
            onClicked: {
                root.openFolderRequested();
                root.close();
            }
        }
    ]
}
