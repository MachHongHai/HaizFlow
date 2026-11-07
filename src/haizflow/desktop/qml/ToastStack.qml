pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import "."

Item {
    id: root
    property int maximumVisible: 4
    property int defaultDuration: 4200
    signal detailsRequested(string title, string message, string tone, string logText)

    function show(title, message, tone, duration, logText) {
        const detail = String(message || "");
        if (ErrorPresentation.isIssue(tone)) {
            for (let i = 0; i < toastModel.count; ++i)
                if (toastModel.get(i).messageText === detail) return;
        }
        while (toastModel.count >= maximumVisible) toastModel.remove(0);
        toastModel.append({titleText: String(title || "HaizFlow"), messageText: detail,
            toneName: String(tone || "info"), technicalLog: String(logText || ""),
            timeoutMs: Math.max(1600, Number(duration || defaultDuration))});
    }
    implicitWidth: 380
    implicitHeight: toastColumn.implicitHeight
    ListModel { id: toastModel }
    Column {
        id: toastColumn
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        spacing: Theme.space8
        Repeater {
            model: toastModel
            delegate: Rectangle {
                id: toast
                objectName: "userErrorToast"
                required property int index
                required property string titleText
                required property string messageText
                required property string toneName
                required property string technicalLog
                required property int timeoutMs
                readonly property bool issue: ErrorPresentation.isIssue(toneName)
                width: toastColumn.width
                height: content.implicitHeight + Theme.space24
                radius: Theme.radius
                color: Theme.surfaceElevated
                border.width: 1
                border.color: Theme.outlineStrong

                ColumnLayout {
                    id: content
                    anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                    anchors.margins: Theme.space12
                    spacing: Theme.space8
                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            id: titleLabel
                            objectName: "toastTitle"
                            Layout.fillWidth: true
                            text: toast.titleText
                            color: Theme.text
                            font.family: Theme.fontFamily
                            font.pixelSize: TypeScale.control
                            font.weight: Font.DemiBold
                            textFormat: Text.PlainText
                            elide: Text.ElideRight
                        }
                        IconButton {
                            objectName: "toastCloseButton"
                            controlSize: 24; iconSize: Theme.iconSmall
                            glyph: IconCatalog.glyph("close"); toolTipText: qsTr("Đóng")
                            onClicked: toastModel.remove(toast.index)
                        }
                    }
                    Text {
                        id: messageLabel
                        objectName: "toastMessage"
                        Layout.fillWidth: true
                        text: toast.issue ? ErrorPresentation.summary(toast.messageText) : toast.messageText
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: TypeScale.label
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                        maximumLineCount: 3
                        elide: Text.ElideRight
                    }
                    RowLayout {
                        objectName: "toastActionRow"
                        Layout.fillWidth: true
                        Layout.topMargin: Theme.space4
                        visible: toast.issue || titleLabel.truncated || messageLabel.truncated
                        spacing: Theme.space8
                        StudioButton {
                            objectName: "toastDetailsButton"
                            text: qsTr("Chi tiết")
                            onClicked: {
                                root.detailsRequested(toast.titleText, toast.messageText, toast.toneName, toast.technicalLog);
                                toastModel.remove(toast.index);
                            }
                        }
                        Item { Layout.fillWidth: true }
                        StudioButton {
                            objectName: "toastConfirmButton"
                            text: qsTr("Xác nhận"); variant: "primary"
                            visible: toast.issue
                            onClicked: toastModel.remove(toast.index)
                        }
                    }
                }
                Timer {
                    interval: toast.timeoutMs
                    running: toast.visible && !toast.issue
                    onTriggered: if (toast.index >= 0 && toast.index < toastModel.count) toastModel.remove(toast.index)
                }
            }
        }
    }
}
