pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import "."

SettingsGroup {
    id: root
    required property var bridge
    property bool permissionsExpanded: false
    readonly property int enabledCount: Number(bridge.permissions.write === true)
        + Number(bridge.permissions.online === true) + Number(bridge.permissions["delete"] === true)
        + Number(bridge.permissions.publish === true)
    title: qsTr("MCP cục bộ")

    SettingRow {
        Layout.fillWidth: true
        label: qsTr("Kết nối với AI agent")
        description: qsTr("Giữ HaizFlow mở khi dùng MCP. Các quyền được bật sẵn và có thể tắt bên dưới.")
        AppSwitch {
            objectName: "mcpEnabledSwitch"
            checked: root.bridge.enabled
            Accessible.name: qsTr("MCP cục bộ")
            onToggled: root.bridge.setEnabled(checked)
        }
    }
    UserErrorNotice {
        Layout.fillWidth: true
        title: qsTr("Kết nối MCP chưa thành công")
        details: root.bridge.error
    }
    StudioButton {
        objectName: "mcpTestConnectionButton"
        text: root.bridge.connectionState === "checking" ? qsTr("Đang kiểm tra…") : qsTr("Kiểm tra HaizFlow")
        enabled: root.bridge.enabled && root.bridge.connectionState !== "checking"
        onClicked: root.bridge.testConnection()
    }
    Text {
        objectName: "mcpConnectionTestResult"
        Layout.fillWidth: true
        visible: root.bridge.connectionMessage.length > 0 && root.bridge.connectionState !== "error"
        text: root.bridge.connectionMessage
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.body
        Accessible.role: Accessible.StaticText
        Accessible.name: text
    }
    UserErrorNotice {
        Layout.fillWidth: true
        title: qsTr("Kiểm tra MCP chưa thành công")
        details: root.bridge.connectionState === "error" ? root.bridge.connectionMessage : ""
    }
    StudioButton {
        objectName: "mcpPermissionsToggle"
        visible: root.bridge.enabled
        text: root.permissionsExpanded ? qsTr("Ẩn quyền truy cập") : qsTr("Quyền của agent · %1/4").arg(root.enabledCount)
        checkable: true
        checked: root.permissionsExpanded
        onClicked: root.permissionsExpanded = !root.permissionsExpanded
    }
    Text {
        Layout.fillWidth: true
        visible: root.bridge.enabled && (root.bridge.permissions["delete"] === true || root.bridge.permissions.publish === true)
        text: qsTr("Lệnh xóa và đăng bài không hỏi lại trong HaizFlow.")
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.body
    }
    ColumnLayout {
        Layout.fillWidth: true
        visible: root.bridge.enabled && root.permissionsExpanded
        spacing: Theme.space16
        SettingRow {
            Layout.fillWidth: true
            label: qsTr("Điều khiển và chỉnh sửa")
            description: qsTr("Tạo dự án, chỉnh sửa, xử lý và xuất video. Tắt để chỉ cho xem.")
            AppSwitch {
                objectName: "mcpWriteSwitch"
                checked: root.bridge.permissions.write === true
                Accessible.name: qsTr("Điều khiển và chỉnh sửa")
                onToggled: root.bridge.setPermission("write", checked)
            }
        }
        SettingRow {
            Layout.fillWidth: true
            label: qsTr("Dịch vụ trực tuyến")
            description: qsTr("Cho phép gọi API, tải video và gói tài nguyên; có thể phát sinh phí API.")
            AppSwitch {
                objectName: "mcpOnlineSwitch"
                checked: root.bridge.permissions.online === true
                Accessible.name: qsTr("Dịch vụ trực tuyến")
                onToggled: root.bridge.setPermission("online", checked)
            }
        }
        SettingRow {
            Layout.fillWidth: true
            label: qsTr("Xóa dự án")
            description: qsTr("Cho phép xóa dự án theo yêu cầu.")
            AppSwitch {
                objectName: "mcpDeleteSwitch"
                checked: root.bridge.permissions["delete"] === true
                Accessible.name: qsTr("Cho agent yêu cầu xóa dự án")
                onToggled: root.bridge.setPermission("delete", checked)
            }
        }
        SettingRow {
            Layout.fillWidth: true
            label: qsTr("Đăng mạng xã hội")
            description: qsTr("Cho phép đăng video bằng tài khoản đã kết nối.")
            AppSwitch {
                objectName: "mcpPublishSwitch"
                checked: root.bridge.permissions.publish === true
                Accessible.name: qsTr("Cho agent yêu cầu đăng mạng xã hội")
                onToggled: root.bridge.setPermission("publish", checked)
            }
        }
    }
}
