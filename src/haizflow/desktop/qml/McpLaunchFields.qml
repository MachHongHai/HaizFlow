pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root
    required property var bridge
    property string copiedField: ""
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
            objectName: "mcpCopyCommandButton"
            text: root.copiedField === "command" ? qsTr("Đã sao chép") : qsTr("Sao chép command")
            onClicked: {
                root.bridge.copyLaunchField("command");
                root.copiedField = "command";
                copiedFeedback.restart();
            }
        }
    }
    Text {
        Layout.fillWidth: true
        text: qsTr("Arguments · mỗi dòng một đối số")
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.label
        wrapMode: Text.WordWrap
    }
    AppTextArea {
        objectName: "mcpLaunchArguments"
        Layout.fillWidth: true
        Layout.preferredHeight: Math.max(110, contentHeight + topPadding + bottomPadding)
        readOnly: true
        text: root.details.arguments || ""
        accessibleName: qsTr("Arguments của máy chủ MCP")
        font.family: "Consolas"
    }
    StudioButton {
        objectName: "mcpCopyArgumentsButton"
        text: root.copiedField === "arguments" ? qsTr("Đã sao chép") : qsTr("Sao chép arguments")
        onClicked: {
            root.bridge.copyLaunchField("arguments");
            root.copiedField = "arguments";
            copiedFeedback.restart();
        }
    }
    Timer {
        id: copiedFeedback
        interval: 2000
        onTriggered: root.copiedField = ""
    }
    onVisibleChanged: {
        if (!visible) {
            copiedFeedback.stop();
            copiedField = "";
        }
    }
}
