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
    property bool troubleshootingExpanded: false
    property bool showAdvancedConfiguration: false
    readonly property string clientKey: client.currentIndex === 0 ? "codex" : "generic"
    readonly property string configurationText: bridge.configuration(clientKey)
    readonly property string setupInstructions: client.currentIndex === 0
        ? qsTr("Mở ứng dụng Codex trên máy tính → Settings → MCP servers → Add server. Đặt tên haizflow và chọn STDIO. Không chọn Streamable HTTP và không nhập URL.")
        : client.currentIndex === 1
        ? qsTr("Mở Claude Code trong ứng dụng hoặc IDE bạn đang dùng, rồi mở một cuộc trò chuyện. Sao chép yêu cầu kết nối bên dưới và gửi cho Claude để thêm MCP; bạn không cần tự viết file cấu hình.")
        : client.currentIndex === 2
        ? qsTr("Mở Claude Desktop → Settings → Desktop app → Manage cạnh Extensions → Local MCP servers. Ở giao diện cũ, mở Settings → Developer → Edit Config. Chọn Edit Config trong app để mở sẵn cấu hình, rồi dán mục haizflow bên dưới. Không dùng Add custom connector dành cho URL từ xa.")
        : client.currentIndex === 3
        ? qsTr("Mở ứng dụng Antigravity, tại khung trò chuyện agent bấm … → MCP Servers → Manage MCP Servers → View raw config. Dán mục haizflow có sẵn bên dưới vào cấu hình mà app mở; không cần tự tìm hoặc tạo file.")
        : qsTr("Trong ứng dụng agent trên máy này, mở phần cấu hình MCP và chọn server cục bộ dùng stdio. Nếu có ô nhập riêng, điền command và từng phần tử args từ cấu hình bên dưới; không điền URL hoặc cổng HTTP.")
    readonly property string reconnectInstructions: client.currentIndex === 0
        ? qsTr("Bấm Save trong form Add server rồi Restart cho server haizflow. Mở chat mới và xem danh sách MCP; nếu cần, thoát rồi mở lại Codex. Cho phép sử dụng công cụ khi app hỏi.")
        : client.currentIndex === 1
        ? qsTr("Duyệt thay đổi thêm server nếu Claude hỏi. Mở lại cuộc trò chuyện hoặc kết nối lại MCP, nhập /mcp để kiểm tra server haizflow. Yêu cầu Claude gọi haizflow_status trước khi giao tác vụ xử lý video.")
        : client.currentIndex === 2
        ? qsTr("Lưu cấu hình, thoát hẳn Claude Desktop rồi mở lại. Kiểm tra server haizflow trong phần Developer và cho phép sử dụng công cụ nếu ứng dụng hỏi.")
        : client.currentIndex === 3
        ? qsTr("Lưu cấu hình rồi quay lại MCP Servers, làm mới danh sách và bật server haizflow. Nếu chưa nạp công cụ, khởi động lại Antigravity và mở cuộc trò chuyện mới.")
        : qsTr("Lưu cấu hình và kết nối lại server haizflow. Agent sẽ tự khởi chạy tiến trình stdio; không cần chạy thêm HaizFlow, Python hay một server HTTP bằng tay.")
    title: qsTr("Hướng dẫn kết nối")

    StudioComboBox {
        id: client
        objectName: "mcpGuideClient"
        Layout.fillWidth: true
        model: [qsTr("Codex"), qsTr("Claude Code"), qsTr("Claude Desktop"), qsTr("Antigravity"), qsTr("MCP khác")]
        Accessible.name: qsTr("Ứng dụng agent")
        onActivated: {
            root.copied = false;
            root.showAdvancedConfiguration = false;
        }
    }
    ZernioSetupStep {
        Layout.fillWidth: true
        stepNumber: 1
        title: qsTr("Bật MCP và chọn quyền")
        description: qsTr("Bật MCP cục bộ ở phần Quyền truy cập rồi tắt những quyền bạn không muốn cấp. Giữ HaizFlow mở; kết nối chỉ dùng được trên máy này và hết hiệu lực khi đóng app.")
    }
    ZernioSetupStep {
        Layout.fillWidth: true
        stepNumber: 2
        title: qsTr("Mở ứng dụng AI agent và thêm MCP")
        description: root.setupInstructions
    }
    ZernioSetupStep {
        Layout.fillWidth: true
        stepNumber: 3
        title: client.currentIndex === 0 ? qsTr("Điền thông tin vào form Add server")
            : client.currentIndex === 1 ? qsTr("Gửi yêu cầu kết nối cho Claude Code") : qsTr("Dán cấu hình HaizFlow có sẵn")
        description: client.currentIndex === 0
            ? qsTr("Dán command vào ô Command. Thêm các arguments theo đúng thứ tự bên dưới, mỗi phần tử một đối số. Đây là thông tin của bản HaizFlow trên máy bạn; không cần tự soạn file.")
            : client.currentIndex === 1
            ? qsTr("Dán toàn bộ yêu cầu này vào chat Claude Code. Claude sẽ thực hiện bước thêm server bằng công cụ của nó; vẫn giữ nguyên quyền duyệt thay đổi trong ứng dụng agent.")
            : qsTr("Sao chép cấu hình bên dưới vào màn hình mà agent vừa mở. Nếu đã có các server khác, chỉ thêm hoặc cập nhật mục haizflow trong mcpServers; không xóa phần còn lại và không tạo mục trùng.")
    }
    McpLaunchFields {
        Layout.fillWidth: true
        visible: client.currentIndex === 0
        bridge: root.bridge
    }
    StudioButton {
        visible: client.currentIndex === 0
        text: root.showAdvancedConfiguration ? qsTr("Ẩn cấu hình nâng cao") : qsTr("Xem cấu hình nâng cao")
        onClicked: root.showAdvancedConfiguration = !root.showAdvancedConfiguration
    }
    ScrollView {
        Layout.fillWidth: true
        Layout.preferredHeight: client.currentIndex === 1 ? 260 : 220
        visible: client.currentIndex !== 0 || root.showAdvancedConfiguration
        contentWidth: availableWidth
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        AppTextArea {
            objectName: "mcpGuideConfiguration"
            text: client.currentIndex === 1 ? root.bridge.setupPrompt : root.configurationText
            readOnly: true
            font.family: "Consolas"
            accessibleName: qsTr("Cấu hình MCP HaizFlow")
        }
    }
    RowLayout {
        Layout.fillWidth: true
        visible: client.currentIndex !== 0 || root.showAdvancedConfiguration
        Item { Layout.fillWidth: true }
        StudioButton {
            objectName: "mcpGuideCopyButton"
            text: root.copied ? qsTr("Đã sao chép")
                : client.currentIndex === 1 ? qsTr("Sao chép yêu cầu kết nối") : qsTr("Sao chép cấu hình")
            onClicked: {
                if (client.currentIndex === 1)
                    root.bridge.copySetupPrompt();
                else
                    root.bridge.copyConfiguration(root.clientKey);
                root.copied = true;
            }
        }
    }
    ZernioSetupStep {
        Layout.fillWidth: true
        stepNumber: 4
        title: qsTr("Nạp lại kết nối trong agent")
        description: root.reconnectInstructions
    }
    ZernioSetupStep {
        Layout.fillWidth: true
        stepNumber: 5
        title: qsTr("Thử bằng một yêu cầu chỉ đọc")
        description: qsTr("Nhập vào chat agent: “Gọi haizflow_status và liệt kê các dự án HaizFlow, chỉ đọc dữ liệu, không chỉnh sửa, xóa hay đăng bài.” Khi nhận được trạng thái và danh sách dự án là kết nối đã hoạt động. Không cần nhập API key để thử bước này.")
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
        text: qsTr("Không thấy server: kiểm tra đúng file cấu hình, cú pháp JSON/TOML và nạp lại agent.\n\nKhông kết nối được với app: mở HaizFlow, bật MCP và chạy agent bằng cùng tài khoản Windows. Chỉ mở một HaizFlow dùng cùng thư mục dữ liệu.\n\nLỗi command/không tìm thấy file: sau khi cập nhật hoặc chuyển thư mục app, sao chép lại cấu hình mới ở đây; không dùng đường dẫn của máy khác.\n\nThiếu quyền: bật lại quyền tương ứng trong Quyền truy cập. Agent không thể tự bật các quyền này.\n\nXử lý, xóa và đăng bài: agent thực hiện lệnh trực tiếp theo quyền đang bật, không có bước xác nhận lại trong trang MCP. Hãy nêu rõ dự án, video và nội dung trong yêu cầu của bạn.\n\nTác vụ đã nhận nhưng chưa xong: yêu cầu agent đọc trạng thái; không gửi lặp lệnh xử lý hoặc đăng bài khi chưa biết kết quả.")
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.body
    }
}
