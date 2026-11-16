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
        objectName: "mcpArgumentsInstruction"
        Layout.fillWidth: true
        text: qsTr("Arguments · %1 mục riêng biệt").arg((root.details.argumentItems || []).length)
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.label
        wrapMode: Text.WordWrap
    }
    Repeater {
        model: root.details.argumentItems || []
        delegate: RowLayout {
            id: argumentRow
            required property int index
            required property string modelData
            Layout.fillWidth: true
            spacing: Theme.space8
            Text {
                text: qsTr("Mục %1").arg(argumentRow.index + 1)
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.label
            }
            AppTextField {
                objectName: "mcpLaunchArgument" + argumentRow.index
                Layout.fillWidth: true
                readOnly: true
                text: argumentRow.modelData
                font.family: "Consolas"
                accessibleName: qsTr("Argument %1").arg(argumentRow.index + 1)
            }
            StudioButton {
                objectName: "mcpCopyArgumentButton" + argumentRow.index
                Layout.minimumWidth: Theme.space32 * 3
                text: root.copiedField === "argument:" + argumentRow.index ? qsTr("Đã sao chép") : qsTr("Sao chép")
                Accessible.name: qsTr("Sao chép Argument %1").arg(argumentRow.index + 1)
                onClicked: {
                    root.bridge.copyLaunchArgument(argumentRow.index);
                    root.copiedField = "argument:" + argumentRow.index;
                    copiedFeedback.restart();
                }
            }
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
