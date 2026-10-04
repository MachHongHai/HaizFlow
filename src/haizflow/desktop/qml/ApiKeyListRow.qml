pragma ComponentBehavior: Bound
// qmllint disable missing-property
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Rectangle {
    id: root
    required property var credential
    property bool zernio: false
    property bool locked: false
    readonly property string checkResult: String(credential.check_result || "")
    readonly property bool checked: checkResult.length > 0 && checkResult !== "checking"
    readonly property string checkDescription: checkResult === "verified" ? qsTr("Kiểm tra thành công")
        : checkResult === "checking" ? qsTr("Đang kiểm tra")
        : checked ? qsTr("Kiểm tra thất bại") : qsTr("Chưa kiểm tra")
    signal removeRequested(string id, string label)
    implicitHeight: 60
    color: Theme.surface
    radius: Theme.radiusSmall
    border.color: Theme.divider
    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.space16
        anchors.rightMargin: Theme.space12
        spacing: Theme.space12
        Rectangle {
            objectName: "zernioKeyStatusDot_" + root.credential.id
            Layout.preferredWidth: 8
            Layout.preferredHeight: 8
            radius: 4
            visible: root.zernio
            color: !root.checked ? Theme.textMuted : root.checkResult === "verified" ? Theme.success : Theme.danger
            Accessible.role: Accessible.StaticText
            Accessible.name: root.checkDescription
            ToolTip.visible: statusHover.hovered
            ToolTip.text: root.checkDescription
            HoverHandler { id: statusHover }
        }
        Text {
            Layout.fillWidth: true
            text: root.credential.label
            textFormat: Text.PlainText
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.body
            elide: Text.ElideRight
        }
        Text {
            visible: root.credential.active
            text: qsTr("Mặc định")
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.label
        }
        StudioButton {
            visible: !root.credential.active
            text: qsTr("Sử dụng")
            enabled: !root.locked
            onClicked: {
                if (root.zernio) AppController.selectZernioApiKey(root.credential.id);
                else AppController.selectGeminiApiKey(root.credential.id);
            }
        }
        StudioButton {
            text: qsTr("Xóa")
            enabled: !root.locked
            onClicked: root.removeRequested(root.credential.id, root.credential.label)
        }
    }
}
