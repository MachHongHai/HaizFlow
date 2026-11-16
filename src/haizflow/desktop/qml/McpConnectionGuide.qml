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
    readonly property bool usesSetupPrompt: client.currentIndex === 1 || client.currentIndex === 3 || client.currentIndex === 4
    readonly property string clientKey: ["codex", "claude-code", "claude-desktop", "antigravity-ide", "antigravity-app", "generic"][client.currentIndex] || "generic"
    readonly property string configurationText: bridge.configuration(clientKey)
    readonly property string setupInstructions: client.currentIndex === 0
        ? qsTr("Mở Codex → Settings → MCP servers → Add server. Chọn STDIO và đặt tên haizflow.")
        : client.currentIndex === 1
        ? qsTr("Mở một cuộc trò chuyện Claude Code trong app hoặc IDE. Gửi yêu cầu kết nối bên dưới và duyệt thay đổi nếu Claude hỏi.")
        : client.currentIndex === 2
        ? qsTr("Mở Claude Desktop trên máy → Settings → Developer → Edit Config (một số bản ghi Local MCP servers). Không dùng trang Connectors trên web.")
        : client.currentIndex === 3
        ? qsTr("Mở một cuộc trò chuyện trong khung agent của Antigravity IDE trên máy này.")
        : client.currentIndex === 4
        ? qsTr("Mở Antigravity App trên máy này và bắt đầu một cuộc trò chuyện với agent.")
        : qsTr("Mở cài đặt MCP trong ứng dụng agent, thêm server cục bộ tên haizflow và chọn STDIO.")
    readonly property string reconnectInstructions: client.currentIndex === 0
        ? qsTr("Bấm Save → Restart cho server haizflow, rồi mở chat mới và gửi câu thử bên dưới. Kết nối đúng sẽ không mở thêm cửa sổ HaizFlow.")
        : client.currentIndex === 1
        ? qsTr("Mở lại cuộc trò chuyện và nhập /mcp để kiểm tra haizflow. Sau đó gửi câu thử bên dưới.")
        : client.currentIndex === 2
        ? qsTr("Lưu cấu hình, thoát hẳn Claude Desktop rồi mở lại. Gửi câu thử trong chat.")
        : client.currentIndex === 3
        ? qsTr("Sau khi agent lưu xong: … ở khung agent → MCP Servers → Manage MCP Servers → làm mới. Mở chat mới và gửi câu thử bên dưới.")
        : client.currentIndex === 4
        ? qsTr("Lưu cấu hình rồi chọn Restart ở menu ⋮ của haizflow trong MCP Servers. Gửi câu thử trong chat.")
        : qsTr("Lưu và kết nối lại haizflow, rồi gửi câu thử.")
    title: qsTr("Hướng dẫn kết nối")
    readonly property string manualInstructions: client.currentIndex === 3
        ? qsTr("Antigravity IDE: … ở khung agent → MCP Servers → Manage MCP Servers → View raw config.")
        : client.currentIndex === 4
        ? qsTr("Antigravity App: Customizations → Installed → MCP Servers → Copy Config File Path; mở tệp vừa sao chép đường dẫn.")
        : client.currentIndex === 1
        ? qsTr("Claude Code: mở .mcp.json trong thư mục dự án và thêm haizflow vào mcpServers. Khi mở lại dự án, cho phép server nếu Claude hỏi.")
        : qsTr("Dùng cấu hình bên dưới trong tệp cấu hình MCP, không dán vào ô Command hay Arguments.")

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
        title: root.usesLaunchFields ? qsTr("Điền Command và từng Argument")
            : root.usesSetupPrompt ? qsTr("Gửi yêu cầu kết nối cho agent") : qsTr("Thêm cấu hình haizflow")
        description: root.usesLaunchFields
            ? qsTr("Dán Command vào ô Command. Trong Arguments, thêm từng mục theo đúng thứ tự bên dưới (bấm + hoặc Add nếu có). Mỗi mục chỉ dán một giá trị; không gộp tất cả vào một ô.")
            : root.usesSetupPrompt
            ? qsTr("Bấm sao chép rồi dán vào cuộc trò chuyện. Cho phép agent cập nhật cấu hình MCP khi được hỏi; chờ lưu xong rồi làm bước 3.")
            : qsTr("Tệp mới: dán toàn bộ cấu hình bên dưới. Nếu đã có mcpServers, chỉ thêm hoặc thay mục haizflow bên trong đó; giữ nguyên các mục khác và mảng args, không tạo mcpServers thứ hai.")
    }
    McpLaunchFields {
        Layout.fillWidth: true
        visible: root.usesLaunchFields
        bridge: root.bridge
    }
    StudioButton {
        objectName: "mcpGuideCopySetupButton"
        visible: root.usesSetupPrompt && !root.showAdvancedConfiguration
        variant: "primary"
        text: root.copied ? qsTr("Đã sao chép") : qsTr("Sao chép yêu cầu kết nối")
        onClicked: {
            root.bridge.copySetupPromptFor(root.clientKey);
            root.copied = true;
        }
    }
    StudioButton {
        objectName: "mcpGuideAdvancedToggle"
        visible: root.usesLaunchFields || root.usesSetupPrompt
        text: root.showAdvancedConfiguration ? qsTr("Thu gọn") : qsTr("Cấu hình thủ công")
        onClicked: {
            root.showAdvancedConfiguration = !root.showAdvancedConfiguration;
            root.copied = false;
        }
    }
    Text {
        objectName: "mcpManualInstructions"
        Layout.fillWidth: true
        visible: root.showAdvancedConfiguration
        text: root.manualInstructions + "\n" + qsTr("Giữ nguyên các server khác. Mỗi phần tử trong args là một đối số riêng.")
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.body
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
            text: root.configurationText
            readOnly: true
            font.family: "Consolas"
            accessibleName: qsTr("Cấu hình MCP HaizFlow")
        }
    }
    StudioButton {
        objectName: "mcpGuideCopyButton"
        visible: (!root.usesLaunchFields && !root.usesSetupPrompt) || root.showAdvancedConfiguration
        text: root.copied ? qsTr("Đã sao chép") : qsTr("Sao chép cấu hình")
        onClicked: {
            root.bridge.copyConfiguration(root.clientKey);
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
        text: qsTr("HaizFlow tự mở thêm cửa sổ: kiểm tra Arguments, mỗi mục phải là một giá trị riêng.\n\nKhông thấy haizflow: lưu cấu hình rồi Restart server hoặc mở chat mới.\n\nKhông kết nối được: giữ HaizFlow mở và bật MCP.\n\nLỗi sau khi cập nhật app: sao chép lại thông tin kết nối từ đây.\n\nThiếu quyền: mở Quyền của agent ở trên và bật quyền cần dùng.")
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.body
    }
}
