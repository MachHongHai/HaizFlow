pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

SettingsGroup {
    id: root
    objectName: "mcpConnectionGuide"
    required property var bridge
    property bool copied: false
    property bool testCopied: false
    property bool troubleshootingExpanded: false
    property bool showAdvancedConfiguration: false
    readonly property bool usesLaunchFields: client.currentIndex === 0 || client.currentIndex === 5
    readonly property bool usesSetupPrompt: client.currentIndex === 1
    readonly property string clientKey: client.currentIndex === 0 ? "codex" : "generic"
    readonly property string configurationText: bridge.configuration(clientKey)
    readonly property string setupInstructions: client.currentIndex === 0
        ? qsTr("Mở Codex → Settings → MCP servers → Add server. Chọn STDIO và đặt tên haizflow.")
        : client.currentIndex === 1
        ? qsTr("Mở một cuộc trò chuyện Claude Code trong app hoặc IDE. Gửi yêu cầu kết nối bên dưới và duyệt thay đổi nếu Claude hỏi.")
        : client.currentIndex === 2
        ? qsTr("Mở Claude Desktop → Settings, tìm Local MCP servers hoặc Developer rồi chọn Edit Config.")
        : client.currentIndex === 3
        ? qsTr("Trong Antigravity IDE: … ở khung agent → MCP Servers → Manage MCP Servers → View raw config.")
        : client.currentIndex === 4
        ? qsTr("Trong Antigravity App: Customizations → Installed → MCP Servers → Copy Config File Path. Mở tệp ở đường dẫn vừa sao chép.")
        : qsTr("Mở cài đặt MCP trong ứng dụng agent, thêm server cục bộ tên haizflow và chọn STDIO.")
    readonly property string reconnectInstructions: client.currentIndex === 0
        ? qsTr("Bấm Save → Restart cho server haizflow, rồi mở chat mới. Gửi câu thử bên dưới.")
        : client.currentIndex === 1
        ? qsTr("Mở lại cuộc trò chuyện và nhập /mcp để kiểm tra haizflow. Sau đó gửi câu thử bên dưới.")
        : client.currentIndex === 2
        ? qsTr("Lưu cấu hình, thoát hẳn Claude Desktop rồi mở lại. Gửi câu thử trong chat.")
        : client.currentIndex === 3
        ? qsTr("Lưu cấu hình rồi làm mới trong MCP Servers. Nếu chưa thấy công cụ, mở lại Antigravity IDE.")
        : client.currentIndex === 4
        ? qsTr("Lưu cấu hình rồi chọn Restart ở menu ⋮ của haizflow trong MCP Servers. Gửi câu thử trong chat.")
        : qsTr("Lưu và kết nối lại haizflow, rồi gửi câu thử.")
    title: qsTr("Hướng dẫn kết nối")

    StudioComboBox {
        id: client
        objectName: "mcpGuideClient"
        Layout.fillWidth: true
        model: [qsTr("Codex"), qsTr("Claude Code"), qsTr("Claude Desktop"), qsTr("Antigravity IDE"), qsTr("Antigravity App"), qsTr("MCP khác")]
        Accessible.name: qsTr("Ứng dụng agent")
        onActivated: {
            root.copied = false;
            root.testCopied = false;
            root.showAdvancedConfiguration = false;
        }
    }
    ZernioSetupStep {
        Layout.fillWidth: true
        stepNumber: 1
        title: qsTr("Thêm HaizFlow vào ứng dụng agent")
        description: root.setupInstructions
    }
    ZernioSetupStep {
        Layout.fillWidth: true
        stepNumber: 2
        title: root.usesLaunchFields ? qsTr("Điền thông tin kết nối")
            : root.usesSetupPrompt ? qsTr("Sao chép và gửi cho Claude Code") : qsTr("Thêm cấu hình haizflow")
        description: root.usesLaunchFields
            ? qsTr("Sao chép Command và Arguments vào các ô tương ứng trong ứng dụng.")
            : root.usesSetupPrompt
            ? qsTr("Bấm sao chép rồi dán vào cuộc trò chuyện Claude Code.")
            : qsTr("Dán cấu hình bên dưới. Nếu đã có server khác, chỉ thêm mục haizflow; giữ nguyên các mục còn lại.")
    }
    McpLaunchFields {
        Layout.fillWidth: true
        visible: root.usesLaunchFields
        bridge: root.bridge
    }
    StudioButton {
        objectName: "mcpGuideAdvancedToggle"
        visible: root.usesLaunchFields || root.usesSetupPrompt
        text: root.showAdvancedConfiguration ? qsTr("Thu gọn") : qsTr("Xem nội dung")
        onClicked: root.showAdvancedConfiguration = !root.showAdvancedConfiguration
    }
    ScrollView {
        Layout.fillWidth: true
        Layout.preferredHeight: 160
        visible: (!root.usesLaunchFields && !root.usesSetupPrompt) || root.showAdvancedConfiguration
        contentWidth: availableWidth
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        AppTextArea {
            objectName: "mcpGuideConfiguration"
            text: root.usesSetupPrompt ? root.bridge.setupPrompt : root.configurationText
            readOnly: true
            font.family: "Consolas"
            accessibleName: qsTr("Cấu hình MCP HaizFlow")
        }
    }
    StudioButton {
        objectName: "mcpGuideCopyButton"
        visible: !root.usesLaunchFields || root.showAdvancedConfiguration
        text: root.copied ? qsTr("Đã sao chép")
            : root.usesSetupPrompt ? qsTr("Sao chép yêu cầu kết nối") : qsTr("Sao chép cấu hình")
        onClicked: {
            if (root.usesSetupPrompt) root.bridge.copySetupPrompt();
            else root.bridge.copyConfiguration(root.clientKey);
            root.copied = true;
        }
    }
    ZernioSetupStep {
        Layout.fillWidth: true
        stepNumber: 3
        title: qsTr("Lưu và thử trong agent")
        description: root.reconnectInstructions
    }
    StudioButton {
        objectName: "mcpGuideCopyTestButton"
        text: root.testCopied ? qsTr("Đã sao chép") : qsTr("Sao chép câu thử")
        onClicked: { root.bridge.copyTestPrompt(); root.testCopied = true; }
    }
    StudioButton {
        objectName: "mcpGuideTroubleshootingToggle"
        text: root.troubleshootingExpanded ? qsTr("Ẩn cách khắc phục") : qsTr("Không kết nối được?")
        checkable: true
        checked: root.troubleshootingExpanded
        onClicked: root.troubleshootingExpanded = !root.troubleshootingExpanded
    }
    Text {
        objectName: "mcpGuideTroubleshooting"
        Layout.fillWidth: true
        visible: root.troubleshootingExpanded
        text: qsTr("Không thấy haizflow: lưu cấu hình rồi Restart server hoặc mở chat mới.\n\nKhông kết nối được: giữ HaizFlow mở và bật MCP.\n\nLỗi sau khi cập nhật app: sao chép lại thông tin kết nối từ đây.\n\nThiếu quyền: mở Quyền của agent ở trên và bật quyền cần dùng.")
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.body
    }
}
