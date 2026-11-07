pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import "."

SettingsGroup {
    id: root
    required property var bridge
    title: qsTr("Quyền truy cập")

    SettingRow {
        Layout.fillWidth: true
        label: qsTr("MCP cục bộ")
        description: qsTr("Bật MCP sẽ bật tất cả quyền bên dưới trong phiên này. Bạn có thể tắt riêng từng quyền; dịch vụ trực tuyến có thể phát sinh phí API.")
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
        text: root.bridge.connectionState === "checking" ? qsTr("Đang kiểm tra…") : qsTr("Kiểm tra kết nối MCP")
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
    ColumnLayout {
        Layout.fillWidth: true
        visible: root.bridge.enabled
        spacing: Theme.space16
        SettingRow {
            Layout.fillWidth: true
            label: qsTr("Điều khiển và chỉnh sửa")
            description: qsTr("Tạo dự án, chỉnh phụ đề, xử lý và xuất video. Tắt quyền này để chỉ cho đọc; các quyền còn lại cũng được tắt.")
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
            description: qsTr("Agent xóa dự án được chỉ định ngay khi gọi lệnh, không hỏi lại trong app.")
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
            description: qsTr("Agent đăng các video được chỉ định với tài khoản và cấu hình hiện tại, không hỏi lại trong app.")
            AppSwitch {
                objectName: "mcpPublishSwitch"
                checked: root.bridge.permissions.publish === true
                Accessible.name: qsTr("Cho agent yêu cầu đăng mạng xã hội")
                onToggled: root.bridge.setPermission("publish", checked)
            }
        }
    }
}
