pragma ComponentBehavior: Bound
// qmllint disable missing-property
import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root
    objectName: "apiKeyCredentialRow"
    required property var credential
    property bool zernio: false
    property bool locked: false
    readonly property string checkResult: String(credential.check_result || "")
    readonly property bool checked: checkResult.length > 0 && checkResult !== "checking"
    readonly property string checkDescription: checkResult === "verified" ? qsTr("API key hợp lệ")
        : checkResult === "checking" ? qsTr("Đang kiểm tra…")
        : checkResult === "invalid" || checkResult === "format-error" ? qsTr("API key không hợp lệ hoặc đã bị thu hồi")
        : checkResult === "permissions" ? qsTr("API key thiếu quyền truy cập")
        : checkResult === "rate-limit" || checkResult === "rate-limited" ? qsTr("Dịch vụ đang giới hạn yêu cầu. Thử lại sau.")
        : checkResult === "billing-required" ? qsTr("Cần kiểm tra số dư hoặc thanh toán")
        : checkResult === "unsupported-check" ? qsTr("Chưa xác minh được API key")
        : checked ? qsTr("Kiểm tra thất bại") : qsTr("Chưa kiểm tra")
    signal removeRequested(string id, string label)
    implicitHeight: Math.max(76, content.implicitHeight + Theme.space32)
    color: Theme.surface
    radius: Theme.radiusSmall
    border.color: Theme.divider
    GridLayout {
        id: content
        anchors.fill: parent
        anchors.margins: Theme.space16
        columns: root.width < 520 ? 1 : 2
        columnSpacing: Theme.space24
        rowSpacing: Theme.space12
        ColumnLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            spacing: Theme.space8
            Item {
                id: heading
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                implicitHeight: Math.max(keyName.implicitHeight, defaultLabel.implicitHeight)
                Text {
                    id: keyName
                    objectName: "apiKeyName_" + root.credential.id
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    width: Math.min(implicitWidth, Math.max(0, heading.width
                        - (defaultLabel.visible ? defaultLabel.implicitWidth + Theme.space8 : 0)))
                    text: root.credential.label
                    textFormat: Text.PlainText
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.body
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }
                Text {
                    id: defaultLabel
                    objectName: "apiKeyDefault_" + root.credential.id
                    anchors.left: keyName.right
                    anchors.leftMargin: Theme.space8
                    anchors.verticalCenter: parent.verticalCenter
                    visible: root.credential.active
                    text: qsTr("Mặc định")
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.metadata
                }
            }
            RowLayout {
                Layout.fillWidth: true
                visible: root.checkResult.length > 0
                spacing: Theme.space8
                Rectangle {
                    objectName: "zernioKeyStatusDot_" + root.credential.id
                    Layout.preferredWidth: 6
                    Layout.preferredHeight: 6
                    radius: 3
                    color: !root.checked ? Theme.textMuted : root.checkResult === "verified" ? Theme.success : Theme.danger
                    Accessible.ignored: true
                }
                Text {
                    Layout.fillWidth: true
                    text: root.checkDescription
                    wrapMode: Text.WordWrap
                    color: root.checkResult === "verified" ? Theme.success : Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.metadata
                }
            }
        }
        RowLayout {
            objectName: "apiKeyActions_" + root.credential.id
            Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
            spacing: Theme.space8
            StudioButton {
                objectName: "useApiKeyButton_" + root.credential.id
                visible: !root.credential.active
                text: qsTr("Sử dụng")
                enabled: !root.locked
                onClicked: {
                    if (root.zernio) AppController.selectZernioApiKey(root.credential.id);
                    else AppController.selectGeminiApiKey(root.credential.id);
                }
            }
            StudioButton {
                objectName: "verifyApiKeyButton_" + root.credential.id
                text: qsTr("Kiểm tra")
                enabled: !root.locked
                onClicked: root.zernio ? AppController.verifyZernioApiKey(root.credential.id)
                    : AppController.verifyGeminiApiKey(root.credential.id)
            }
            StudioIconButton {
                objectName: "removeApiKeyButton_" + root.credential.id
                iconName: "delete"
                controlSize: 36
                toolTipText: qsTr("Xóa")
                showToolTip: true
                enabled: !root.locked
                onClicked: root.removeRequested(root.credential.id, root.credential.label)
            }
        }
    }
}
