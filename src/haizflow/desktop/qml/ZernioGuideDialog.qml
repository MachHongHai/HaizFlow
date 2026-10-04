pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root
    objectName: "zernioApiGuide"

    title: qsTr("Thiết lập Zernio")
    subtitle: qsTr("Kết nối tài khoản để đăng video")
    preferredWidth: 620
    maximumWidth: 660
    maximumHeight: 620

    ZernioSetupStep {
        Layout.fillWidth: true
        stepNumber: 1
        title: qsTr("Đăng nhập Zernio")
        description: qsTr("Mở trang quản lý Zernio trong trình duyệt.")

        StudioButton {
            variant: "secondary"
            text: qsTr("Mở Zernio")
            onClicked: AppController.openZernioSignIn()
        }
    }

    ZernioSetupStep {
        Layout.fillWidth: true
        stepNumber: 2
        title: qsTr("Thêm API key")
        description: qsTr("Tạo key có quyền đọc và ghi. Sao chép ngay khi tạo; Zernio chỉ hiển thị key một lần.")

        StudioButton {
            variant: "secondary"
            text: qsTr("Mở trang API key")
            onClicked: AppController.openZernioApiKeys()
        }
    }

    ZernioSetupStep {
        Layout.fillWidth: true
        stepNumber: 3
        title: qsTr("Lưu key và chọn tài khoản")
        description: qsTr("Lưu key tại Cài đặt → API Key → Zernio. Sau đó mở dự án đăng mạng xã hội và chọn tài khoản.")
    }

    footerActions: [
        StudioButton {
            text: qsTr("Tài liệu Zernio")
            variant: "ghost"
            onClicked: AppController.openZernioPostingDocs()
        },
        StudioButton {
            text: qsTr("Đóng")
            variant: "primary"
            onClicked: root.close()
        }
    ]
}
