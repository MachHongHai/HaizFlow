import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    required property string timestamp
    required property string severity
    required property string stage
    required property string title
    required property string detail
    required property int progress
    required property string code

    implicitHeight: detail.length > 0 ? 48 : 32
    color: "transparent"

    RowLayout {
        anchors.fill: parent
        spacing: Theme.space8

        FluentIcon {
            Layout.preferredWidth: 16
            Layout.preferredHeight: 16
            name: root.severity === "error" ? "error"
                : root.severity === "warning" ? "warning" : "info"
            iconColor: root.severity === "error" ? Theme.danger
                : root.severity === "warning" ? Theme.warning : Theme.textMuted
            iconSize: 14
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 1

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space8
                Text {
                    Layout.fillWidth: true
                    text: root.title
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.control
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                }
                Text {
                    text: root.timestamp
                    color: Theme.textDisabled
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.metadata
                    textFormat: Text.PlainText
                }
            }

            Text {
                Layout.fillWidth: true
                visible: root.detail.length > 0
                text: root.detail
                color: root.severity === "error" ? Theme.danger : Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.metadata
                textFormat: Text.PlainText
                elide: Text.ElideRight
            }
        }

        Text {
            visible: root.progress >= 0
            text: qsTr("%1%").arg(root.progress)
            color: Theme.interactive
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.metadata
            font.weight: Font.DemiBold
            textFormat: Text.PlainText
        }
    }

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 1
        color: Theme.divider
    }
}
