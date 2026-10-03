pragma ComponentBehavior: Bound
// qmllint disable missing-property

import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root
    title: qsTr("Lấy Gemini API key")
    subtitle: qsTr("Google AI Studio")
    preferredWidth: 600
    maximumWidth: 640

    ZernioSetupStep {
        Layout.fillWidth: true
        stepNumber: 1
        title: qsTr("Mở Google AI Studio")
        description: qsTr("Đăng nhập tài khoản Google và mở trang API keys.")
        statusText: qsTr("Trình duyệt")
        statusTone: "muted"
        StudioButton {
            text: qsTr("Mở trang API keys")
            variant: "secondary"
            onClicked: AppController.openGeminiApiKeys()
        }
    }

    ZernioSetupStep {
        Layout.fillWidth: true
        stepNumber: 2
        title: qsTr("Tạo và sao chép key")
        description: qsTr("Chọn dự án Google của bạn, tạo key mới và sao chép. Kiểm tra hạn mức sử dụng trong AI Studio.")
        statusText: qsTr("AI Studio")
        statusTone: "muted"
    }

    ZernioSetupStep {
        Layout.fillWidth: true
        stepNumber: 3
        title: qsTr("Lưu key trong HaizFlow")
        description: qsTr("Đặt tên, dán và lưu key trong Cài đặt → API Key. Bạn có thể thêm nhiều key và chọn key đang dùng. Key không nằm trong dự án.")
        statusText: AppController.geminiKeyConfigured ? qsTr("Đã lưu") : qsTr("Chưa lưu")
        statusTone: AppController.geminiKeyConfigured ? "success" : "warning"
    }

    Text {
        Layout.fillWidth: true
        text: qsTr("Free Tier có hạn mức riêng. HaizFlow không xác định được gói thanh toán từ API key. Kiểm tra giá và hạn mức trước khi chạy tác vụ dài.")
        color: Theme.textMuted
        font.pixelSize: TypeScale.metadata
        wrapMode: Text.WordWrap
    }
    ExternalTextLink {
        text: qsTr("Bảng giá và hạn mức Gemini")
        destination: "https://ai.google.dev/gemini-api/docs/pricing"
    }

    footerActions: [
        StudioButton {
            text: qsTr("Đóng")
            variant: "primary"
            onClicked: root.close()
        }
    ]
}
