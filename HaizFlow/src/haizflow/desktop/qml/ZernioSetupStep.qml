pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    required property int stepNumber
    required property string title
    required property string description
    required property string statusText
    property string statusTone: "muted"
    default property alias actions: actionRow.data

    readonly property color statusColor: statusTone === "success" ? Theme.success
        : statusTone === "warning" ? Theme.warning
        : statusTone === "danger" ? Theme.danger
        : Theme.textSubtle
    readonly property color statusSurface: statusTone === "success" ? Theme.successMuted
        : statusTone === "warning" ? Theme.warningMuted
        : statusTone === "danger" ? Theme.dangerMuted
        : Theme.surfaceMuted

    implicitHeight: 90
    radius: Theme.radius
    color: Theme.surfaceElevated
    border.width: 1
    border.color: Theme.outline

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.space12
        spacing: Theme.space8

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space8

            Rectangle {
                Layout.preferredWidth: 24
                Layout.preferredHeight: 24
                radius: 12
                color: Theme.interactiveMuted

                Text {
                    anchors.centerIn: parent
                    text: String(root.stepNumber)
                    color: Theme.interactive
                    font.pixelSize: Theme.caption
                    font.weight: Font.Bold
                    textFormat: Text.PlainText
                }
            }

            Text {
                Layout.fillWidth: true
                text: root.title
                color: Theme.text
                font.pixelSize: Theme.body
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
                elide: Text.ElideRight
            }

            Rectangle {
                Layout.preferredHeight: 24
                Layout.preferredWidth: statusLabel.implicitWidth + Theme.space16
                radius: 12
                color: root.statusSurface

                Text {
                    id: statusLabel
                    anchors.centerIn: parent
                    text: root.statusText
                    color: root.statusColor
                    font.pixelSize: Theme.label
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space8

            Text {
                Layout.fillWidth: true
                text: root.description
                color: Theme.textMuted
                font.pixelSize: Theme.label
                textFormat: Text.PlainText
                elide: Text.ElideRight
            }

            RowLayout {
                id: actionRow
                spacing: Theme.space8
            }
        }
    }
}
