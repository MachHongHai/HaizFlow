pragma ComponentBehavior: Bound
// qmllint disable missing-property
import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root
    required property var credential
    signal removeRequested(string id, string label)
    readonly property string checkResult: String(credential.check_result || "")
    readonly property string statusText: checkResult === "checking" ? qsTr("Đang kiểm tra…")
        : checkResult === "verified" || checkResult === "model-not-found" ? qsTr("Kết nối thành công")
        : checkResult === "invalid" ? qsTr("API key không hợp lệ hoặc thiếu quyền")
        : checkResult === "unsupported-check" ? qsTr("API không hỗ trợ kiểm tra kết nối")
        : checkResult === "unavailable" ? qsTr("Chưa kết nối được dịch vụ") : ""
    implicitHeight: Math.max(72, content.implicitHeight + Theme.space24)
    color: Theme.surface
    radius: Theme.radiusSmall
    border.color: Theme.divider
    RowLayout {
        id: content
        anchors.fill: parent
        anchors.margins: Theme.space12
        spacing: Theme.space12
        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.space4
            Text {
                Layout.fillWidth: true
                text: root.credential.label
                textFormat: Text.PlainText
                elide: Text.ElideRight
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.body
            }
            Text {
                Layout.fillWidth: true
                visible: root.credential.provider === "custom"
                text: root.credential.base_url
                textFormat: Text.PlainText
                elide: Text.ElideRight
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.label
            }
            Text {
                Layout.fillWidth: true
                visible: root.statusText.length > 0
                text: root.statusText
                wrapMode: Text.WordWrap
                color: root.checkResult === "verified" ? Theme.success : Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.metadata
            }
        }
        StudioButton {
            text: qsTr("Kiểm tra")
            enabled: !AppController.translationApi.busy
            onClicked: AppController.translationApi.verify(root.credential.id)
        }
        StudioButton {
            text: qsTr("Xóa")
            enabled: !root.credential.checking
            onClicked: root.removeRequested(root.credential.id, root.credential.label)
        }
    }
}
