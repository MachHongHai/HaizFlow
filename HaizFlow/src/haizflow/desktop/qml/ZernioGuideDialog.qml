pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root

    signal configureApiKeyRequested()
    signal chooseConnectionRequested()

    title: qsTr("Thiết lập Zernio")
    subtitle: qsTr("Kết nối tài khoản để đăng video")
    preferredWidth: 620
    preferredHeight: 450
    maximumWidth: 660
    maximumHeight: 620

    ZernioSetupStep {
        Layout.fillWidth: true
        stepNumber: 1
        title: qsTr("Đăng nhập Zernio")
        description: qsTr("Mở trang quản lý Zernio trong trình duyệt.")
        statusText: qsTr("Trình duyệt")
        statusTone: "muted"

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
        description: qsTr("Lưu key có quyền đọc và ghi trong HaizFlow.")
        statusText: !AppController.zernioApiKeyConfigured
            ? qsTr("Bắt buộc")
            : AppController.zernioApiKeyVerified ? qsTr("Đã xác minh") : qsTr("Cần xác minh")
        statusTone: AppController.zernioApiKeyVerified ? "success" : "warning"

        StudioButton {
            variant: AppController.zernioApiKeyVerified ? "secondary" : "primary"
            text: qsTr("Quản lý API key")
            onClicked: root.configureApiKeyRequested()
        }
    }

    ZernioSetupStep {
        Layout.fillWidth: true
        stepNumber: 3
        title: qsTr("Kết nối nền tảng")
        description: AppController.zernioConnectedAccountCount > 0
            ? qsTr("Tài khoản đã kết nối sẵn sàng để đăng.")
            : qsTr("Chọn nền tảng và xác nhận trong trình duyệt.")
        statusText: AppController.zernioConnectedAccountCount > 0
            ? qsTr("Đã kết nối: %1").arg(AppController.zernioConnectedAccountCount)
            : qsTr("Chưa kết nối")
        statusTone: AppController.zernioConnectedAccountCount > 0 ? "success" : "muted"

        StudioButton {
            variant: AppController.zernioConnectedAccountCount > 0 ? "secondary" : "primary"
            text: qsTr("Quản lý kết nối")
            enabled: AppController.zernioApiKeyVerified && !AppController.tiktokPublishBusy
            onClicked: root.chooseConnectionRequested()
        }
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
