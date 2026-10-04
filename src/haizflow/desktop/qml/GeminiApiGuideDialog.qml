pragma ComponentBehavior: Bound
// qmllint disable missing-property

import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root
    objectName: "geminiApiGuide"
    title: qsTr("Lấy Gemini API key")
    subtitle: qsTr("Google AI Studio")
    preferredWidth: 600
    maximumWidth: 640

    ZernioSetupStep {
        Layout.fillWidth: true
        stepNumber: 1
        title: qsTr("Mở Google AI Studio")
        description: qsTr("Đăng nhập tài khoản Google và mở trang API keys.")
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
    }

    ZernioSetupStep {
        Layout.fillWidth: true
        stepNumber: 3
        title: qsTr("Lưu key trong HaizFlow")
        description: qsTr("Trong Cài đặt → API Key → Gemini, đặt tên key rồi chọn Lưu và sử dụng.")
    }

    Text {
        Layout.fillWidth: true
        text: qsTr("Chi phí và hạn mức phụ thuộc dự án Google của bạn.")
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
