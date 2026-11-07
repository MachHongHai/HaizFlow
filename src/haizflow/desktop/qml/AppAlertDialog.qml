import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root

    property string alertMessage: ""
    property string severity: "information"
    property string technicalLog: ""
    property var pendingErrors: []
    signal technicalDetailsRequested(string alertTitle, string detail, string logText)
    readonly property bool isError: severity === "critical" || severity === "error" || severity === "danger" || severity === "failed"
    readonly property color accentColor: isError ? Theme.danger
        : severity === "warning" ? Theme.warning : Theme.textMuted

    preferredWidth: 480
    maximumWidth: 520

    function showAlert(alertTitle, message, level, logText) {
        const next = {title: alertTitle || "HaizFlow", message: message || "", level: level || "information", log: logText || ""};
        if (visible) {
            if (alertMessage === next.message) return;
            if (pendingErrors.some(item => item.message === next.message)) return;
            if (pendingErrors.length < 8) pendingErrors = pendingErrors.concat([next]);
            return;
        }
        title = alertTitle || "HaizFlow"
        alertMessage = message || ""
        severity = level || "information"
        technicalLog = logText || ""
        open()
    }
    onClosed: Qt.callLater(function() {
        if (root.pendingErrors.length === 0) return;
        const next = root.pendingErrors[0];
        root.pendingErrors = root.pendingErrors.slice(1);
        root.showAlert(next.title, next.message, next.level, next.log);
    })

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space12

        Text {
            Layout.fillWidth: true
            objectName: "appAlertSummary"
            text: ErrorPresentation.summary(root.alertMessage)
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.body
            lineHeight: 1.45
            horizontalAlignment: Text.AlignLeft
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
        }
    }

    footerActions: [
        StudioButton {
            objectName: "appAlertDetails"
            Layout.minimumWidth: 80
            Layout.preferredHeight: UiMetrics.controlHeight
            text: qsTr("Chi tiết")
            visible: ErrorPresentation.isIssue(root.severity) || ErrorPresentation.technical(root.alertMessage)
                || root.alertMessage.length > 180 || root.alertMessage.indexOf("\n") >= 0
            onClicked: root.technicalDetailsRequested(root.title, root.alertMessage, root.technicalLog)
        },
        StudioButton {
            objectName: "appAlertClose"
            Layout.minimumWidth: 80
            Layout.preferredHeight: UiMetrics.controlHeight
            text: qsTr("Đóng")
            onClicked: root.close()
        },
        StudioButton {
            objectName: "appAlertConfirm"
            Layout.minimumWidth: 88
            Layout.preferredHeight: UiMetrics.controlHeight
            text: qsTr("Xác nhận"); variant: "primary"
            onClicked: root.close()
        }
    ]
}
