pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

Item {
    id: root

    property int maximumVisible: 4
    property int defaultDuration: 4200

    function show(title, message, tone, duration) {
        while (toastModel.count >= maximumVisible)
            toastModel.remove(0)
        toastModel.append({
            titleText: String(title || "HaizFlow"),
            messageText: String(message || ""),
            toneName: String(tone || "info"),
            timeoutMs: Math.max(1600, Number(duration || defaultDuration))
        })
    }

    implicitWidth: 380
    implicitHeight: toastColumn.implicitHeight

    ListModel { id: toastModel }

    Column {
        id: toastColumn
        anchors.fill: parent
        spacing: Theme.space8

        Repeater {
            model: toastModel

            delegate: Rectangle {
                id: toast
                required property int index
                required property string titleText
                required property string messageText
                required property string toneName
                required property int timeoutMs

                width: toastColumn.width
                height: toastContent.implicitHeight + Theme.space16 * 2
                radius: Theme.radius
                color: Theme.surfaceElevated
                border.width: 1
                border.color: toneName === "failed" || toneName === "critical" ? Theme.danger
                    : toneName === "warning" ? Theme.warning : Theme.outlineStrong

                RowLayout {
                    id: toastContent
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.leftMargin: Theme.space16
                    anchors.rightMargin: Theme.space8
                    spacing: Theme.space12

                    FluentIcon {
                        Layout.preferredWidth: 18
                        Layout.preferredHeight: 18
                        name: toast.toneName === "failed" || toast.toneName === "critical" ? "error" : "info"
                        iconColor: toast.toneName === "failed" || toast.toneName === "critical" ? Theme.danger
                            : toast.toneName === "warning" ? Theme.warning : Theme.interactive
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2

                        Text {
                            Layout.fillWidth: true
                            text: toast.titleText
                            color: Theme.text
                            font.family: Theme.fontFamily
                            font.pixelSize: TypeScale.control
                            font.weight: Font.DemiBold
                            textFormat: Text.PlainText
                            elide: Text.ElideRight
                        }
                        Text {
                            Layout.fillWidth: true
                            text: toast.messageText
                            color: Theme.textMuted
                            font.family: Theme.fontFamily
                            font.pixelSize: TypeScale.label
                            textFormat: Text.PlainText
                            wrapMode: Text.WordWrap
                            maximumLineCount: 3
                            elide: Text.ElideRight
                        }
                    }

                    IconButton {
                        glyph: "\uE711"
                        toolTipText: qsTr("Đóng")
                        onClicked: toastModel.remove(toast.index)
                    }
                }

                Timer {
                    interval: toast.timeoutMs
                    running: toast.visible
                    onTriggered: {
                        if (toast.index >= 0 && toast.index < toastModel.count)
                            toastModel.remove(toast.index)
                    }
                }
            }
        }
    }
}
