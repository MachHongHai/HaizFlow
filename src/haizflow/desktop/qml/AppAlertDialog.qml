import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root

    property string alertMessage: ""
    property string severity: "information"
    readonly property bool isError: severity === "critical" || severity === "error" || severity === "danger"
    readonly property color accentColor: isError ? Theme.danger
        : severity === "warning" ? Theme.warning : Theme.textMuted

    preferredWidth: 440
    maximumWidth: 520

    function showAlert(alertTitle, message, level) {
        title = alertTitle || "HaizFlow"
        alertMessage = message || ""
        severity = level || "information"
        open()
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space12

        FluentIcon {
            Layout.alignment: Qt.AlignTop
            Layout.preferredWidth: 20
            Layout.preferredHeight: 20
            name: root.isError ? "error"
                : root.severity === "warning" ? "warning" : "info"
            iconColor: root.accentColor
            iconSize: 18
        }

        Text {
            Layout.fillWidth: true
            text: root.alertMessage
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.control
            lineHeight: 1.35
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
        }
    }

    footerActions: [
        StudioButton {
            text: qsTr("Đóng")
            variant: "primary"
            onClicked: root.close()
        }
    ]
}
