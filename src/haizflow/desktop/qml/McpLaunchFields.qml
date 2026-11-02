pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root
    required property var bridge
    readonly property var details: bridge.launchDetails
    spacing: Theme.space8

    Text {
        Layout.fillWidth: true
        text: qsTr("Tên server: haizflow · Loại kết nối: STDIO")
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.body
        wrapMode: Text.WordWrap
    }
    RowLayout {
        Layout.fillWidth: true
        AppTextField {
            objectName: "mcpLaunchCommand"
            Layout.fillWidth: true
            readOnly: true
            text: root.details.command || ""
            Accessible.name: qsTr("Command của máy chủ MCP")
        }
        StudioButton {
            text: qsTr("Sao chép command")
            onClicked: root.bridge.copyLaunchField("command")
        }
    }
    Text {
        Layout.fillWidth: true
        text: qsTr("Arguments: mỗi dòng dưới đây là một đối số, giữ nguyên thứ tự.")
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.label
        wrapMode: Text.WordWrap
    }
    AppTextArea {
        objectName: "mcpLaunchArguments"
        Layout.fillWidth: true
        Layout.preferredHeight: 110
        readOnly: true
        text: root.details.arguments || ""
        accessibleName: qsTr("Arguments của máy chủ MCP")
        font.family: "Consolas"
    }
    StudioButton {
        text: qsTr("Sao chép arguments")
        onClicked: root.bridge.copyLaunchField("arguments")
    }
}
