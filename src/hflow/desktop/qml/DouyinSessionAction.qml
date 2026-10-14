import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root
    property bool operationBusy: false
    property string url: ""
    // qmllint disable stale-property-read
    property var session: AppController.douyinSession
    // qmllint enable stale-property-read
    spacing: Theme.space8
    readonly property bool requiresSession: root.session.requiresSession(root.url)
    readonly property bool permitsRequest: !root.requiresSession || (root.session.ready && !root.session.busy)

    RowLayout {
        Layout.fillWidth: true
        StudioButton {
            text: root.session.busy ? qsTr("Đang tạo phiên…")
                : root.session.ready ? qsTr("Làm mới phiên") : qsTr("Tạo phiên Douyin")
            variant: "secondary"
            enabled: !root.session.busy && !root.operationBusy
            onClicked: root.session.create()
        }
        StudioButton {
            visible: root.session.busy
            text: qsTr("Hủy")
            variant: "secondary"
            onClicked: root.session.cancel()
        }
        Text {
            Layout.fillWidth: true
            text: root.session.status.length > 0 ? I18n.runtimeStatus(root.session.status)
                : qsTr("Mở phiên trình duyệt riêng cho Douyin. Không dùng tài khoản hoặc dữ liệu trình duyệt cá nhân.")
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.metadata
            color: Theme.textMuted
            wrapMode: Text.Wrap
            textFormat: Text.PlainText
        }
    }
}
