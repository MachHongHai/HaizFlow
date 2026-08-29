import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    property bool canUndo: false
    property bool canRedo: false
    property bool canCommit: false
    property string primaryText: qsTr("Duyệt và tiếp tục")

    signal undoRequested()
    signal redoRequested()
    signal commitRequested()

    implicitHeight: Theme.commandBarHeight
    color: Theme.surface
    border.width: 1
    border.color: Theme.outline
    radius: Theme.radiusSmall

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.space12
        anchors.rightMargin: Theme.space12
        spacing: Theme.space8

        Text {
            Layout.fillWidth: true
            text: qsTr("Tự động lưu thay đổi") + "  ·  " + qsTr("Lăn chuột để thu phóng · Shift+lăn để di chuyển")
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.label
            textFormat: Text.PlainText
            elide: Text.ElideRight
        }

        AppButton {
            text: qsTr("Hoàn tác")
            compact: true
            enabled: root.canUndo
            onClicked: root.undoRequested()
        }

        AppButton {
            text: qsTr("Làm lại")
            compact: true
            enabled: root.canRedo
            onClicked: root.redoRequested()
        }

        AppButton {
            text: root.primaryText
            tone: "primary"
            enabled: root.canCommit
            onClicked: root.commitRequested()
        }
    }
}
