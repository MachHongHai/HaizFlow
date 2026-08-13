pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Dialog {
    id: root

    property string alertTitle: "HaizFlow"
    property string alertMessage: ""
    property string severity: "information"
    readonly property color accentColor: severity === "critical"
        ? Theme.danger
        : severity === "warning" ? Theme.warning : Theme.interactive

    function showAlert(title, message, level) {
        alertTitle = title || "HaizFlow"
        alertMessage = message || ""
        severity = level || "information"
        open()
    }

    modal: true
    focus: true
    width: Math.min(480, parent ? parent.width - 48 : 480)
    padding: 0
    closePolicy: Popup.CloseOnEscape
    parent: Overlay.overlay
    x: Math.round((parent.width - width) / 2)
    y: Math.round((parent.height - implicitHeight) / 2)
    header: null
    footer: null

    enter: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.motionStandard }
            NumberAnimation { property: "scale"; from: 0.97; to: 1; duration: Theme.motionStandard; easing.type: Easing.OutCubic }
        }
    }
    exit: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.motionFast }
            NumberAnimation { property: "scale"; from: 1; to: 0.99; duration: Theme.motionFast }
        }
    }

    background: Rectangle {
        radius: Theme.radius
        color: Theme.surface
        border.width: 1
        border.color: root.accentColor
    }

    contentItem: ColumnLayout {
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.margins: Theme.space24
            spacing: Theme.space16

            Rectangle {
                Layout.alignment: Qt.AlignTop
                Layout.preferredWidth: 40
                Layout.preferredHeight: 40
                radius: 12
                color: root.severity === "critical" ? Theme.dangerMuted
                    : root.severity === "warning" ? Theme.warningMuted : Theme.interactiveMuted

                Text {
                    anchors.centerIn: parent
                    text: root.severity === "information" ? "i" : "!"
                    color: root.accentColor
                    font.pixelSize: Theme.body
                    font.weight: Font.Bold
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: Theme.space8

                Text {
                    Layout.fillWidth: true
                    text: root.alertTitle
                    color: Theme.text
                    font.pixelSize: Theme.h3
                    font.weight: Font.DemiBold
                    wrapMode: Text.WordWrap
                    textFormat: Text.PlainText
                }

                Text {
                    Layout.fillWidth: true
                    text: root.alertMessage
                    color: Theme.textMuted
                    font.pixelSize: Theme.body
                    lineHeight: 1.25
                    wrapMode: Text.WordWrap
                    textFormat: Text.PlainText
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.divider
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.margins: Theme.space16

            Item { Layout.fillWidth: true }

            AppButton {
                text: I18n.t("OK")
                tone: "primary"
                onClicked: root.close()
            }
        }
    }
}
