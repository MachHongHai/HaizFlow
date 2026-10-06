pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Popup {
    id: root
    objectName: "appUpdatePopup"
    property var controller: AppController
    readonly property string state: controller.appUpdateState
    readonly property bool updating: ["downloading", "verifying", "installing", "preparing", "restarting"].indexOf(state) >= 0
    readonly property int phaseProgress: Math.max(0, Math.min(100, Math.round(
        state === "downloading" ? controller.appUpdateDownloadProgress
            * (controller.appUpdateUsesDelta === false ? 1 : 2)
        : state === "verifying" ? (controller.appUpdateDownloadProgress - 50) * 100 / 15
        : state === "preparing" ? (controller.appUpdateDownloadProgress - 65) * 4 : 0)))
    readonly property bool unknownPhaseProgress: controller.appUpdateDetailedProgress === false
        && (state === "verifying" || state === "preparing")
    parent: Overlay.overlay
    width: Math.min(380, parent ? parent.width - Theme.space16 : 380)
    padding: Theme.space16
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnReleaseOutside

    function confirmUpdate() {
        confirmationLoader.requestedVersion = root.controller.latestAppVersion;
        confirmationLoader.requestedState = root.state;
        confirmationLoader.invoke("open", []);
    }

    LazyDialogLoader {
        id: confirmationLoader
        property string requestedVersion: ""
        property string requestedState: ""
        sourceComponent: ConfirmDialog {
            objectName: "appUpdateConfirmationDialog"
            title: confirmationLoader.requestedState === "ready"
                ? qsTr("Khởi động lại để cập nhật?") : qsTr("Tải bản cập nhật?")
            message: confirmationLoader.requestedState === "ready"
                ? qsTr("HaizFlow sẽ đóng và mở lại để áp dụng phiên bản %1. Lưu các thay đổi đang chỉnh sửa trước khi tiếp tục.").arg(confirmationLoader.requestedVersion)
                : qsTr("Tải và kiểm tra phiên bản %1. HaizFlow sẽ hỏi lại trước khi khởi động lại; dự án và gói tài nguyên được giữ nguyên.").arg(confirmationLoader.requestedVersion)
            confirmText: confirmationLoader.requestedState === "ready"
                ? qsTr("Khởi động lại") : qsTr("Tải cập nhật")
            onConfirmed: root.controller.confirmAppUpdate(confirmationLoader.requestedVersion, confirmationLoader.requestedState)
            onClosed: confirmationLoader.release()
        }
    }

    function updateError(source) {
        const messages = {
            "Dừng hoặc chờ các tác vụ hoàn tất trước khi cập nhật.": qsTr("Dừng hoặc chờ các tác vụ hoàn tất trước khi cập nhật."),
            "Cập nhật trực tiếp chỉ dùng trong bản HaizFlow đã cài đặt.": qsTr("Cập nhật trực tiếp chỉ dùng trong bản HaizFlow đã cài đặt."),
            "Bản phát hành chưa có bộ cài Windows kèm mã kiểm tra. Hãy xem chi tiết cập nhật.": qsTr("Bản phát hành chưa có bộ cài Windows kèm mã kiểm tra. Hãy xem chi tiết cập nhật."),
            "Bộ cài chưa có chữ ký hợp lệ. Không thể cập nhật tự động.": qsTr("Bộ cài chưa có chữ ký hợp lệ. Không thể cập nhật tự động."),
            "Bộ cài tải xuống chưa đầy đủ hoặc mã kiểm tra không khớp. Hãy thử lại.": qsTr("Bộ cài tải xuống chưa đầy đủ hoặc mã kiểm tra không khớp. Hãy thử lại."),
            "Bộ cài đã đóng. Nếu cập nhật thành công, hãy khởi động lại HaizFlow.": qsTr("Bộ cài đã đóng. Nếu cập nhật thành công, hãy khởi động lại HaizFlow."),
            "Trạng thái cập nhật đã thay đổi. Kiểm tra lại trước khi xác nhận.": qsTr("Trạng thái cập nhật đã thay đổi. Kiểm tra lại trước khi xác nhận."),
            "Không thể tải bản cập nhật. Kiểm tra kết nối mạng rồi thử lại.": qsTr("Không thể tải bản cập nhật. Kiểm tra kết nối mạng rồi thử lại.")
        };
        return messages[source] || source;
    }

    background: Rectangle {
        radius: Theme.radius
        color: Theme.surfaceElevated
        border.color: Theme.outlineStrong
        border.width: 1
    }
    contentItem: ColumnLayout {
        spacing: Theme.space12
        RowLayout {
            Layout.fillWidth: true
            Text {
                Layout.fillWidth: true
                text: qsTr("Phiên bản mới")
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.section
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
            }
            Text {
                text: root.controller.hasAppUpdate
                    ? "v" + root.controller.latestAppVersion : "v" + root.controller.currentAppVersion
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.metadata
                textFormat: Text.PlainText
            }
        }
        Text {
            id: updateMessage
            objectName: "appUpdateMessage"
            Layout.fillWidth: true
            readonly property string message: root.state === "checking" || root.state === "idle"
                ? qsTr("Đang kiểm tra phiên bản mới…")
                : root.state === "error"
                    ? qsTr("Không thể kiểm tra phiên bản mới. Kiểm tra kết nối mạng rồi thử lại.")
                    : root.state === "no_release" ? qsTr("Chưa có bản phát hành công khai.")
                    : root.controller.hasAppUpdate
                        ? qsTr("Có phiên bản mới.")
                        : qsTr("Bạn đang dùng phiên bản mới nhất.")
            text: message
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.control
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.space4
            Text {
                Layout.fillWidth: true
                text: qsTr("Thông tin chi tiết xem tại:")
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.control
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
            }
            ExternalTextLink {
                objectName: "appUpdateDetailsLink"
                text: "haizflow.pages.dev"
                destination: "https://haizflow.pages.dev/"
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            visible: root.updating
            spacing: Theme.space4
            Text {
                Layout.fillWidth: true
                text: root.state === "downloading"
                    ? qsTr("Đang tải bản cập nhật · %1%").arg(root.phaseProgress)
                    : root.state === "verifying" ? (root.unknownPhaseProgress
                        ? qsTr("Đang kiểm tra bản cập nhật…")
                        : qsTr("Đang kiểm tra bản cập nhật · %1%").arg(root.phaseProgress))
                    : root.state === "preparing" ? (root.unknownPhaseProgress
                        ? qsTr("Đang chuẩn bị phiên bản mới…")
                        : qsTr("Đang chuẩn bị phiên bản mới · %1%").arg(root.phaseProgress))
                    : root.state === "restarting" ? qsTr("Đang khởi động lại HaizFlow…")
                    : qsTr("Bộ cài đã mở. Làm theo hướng dẫn để hoàn tất cập nhật.")
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.metadata
                wrapMode: Text.WordWrap
                textFormat: Text.PlainText
            }
            AppProgressBar {
                Layout.fillWidth: true
                visible: root.state !== "installing"
                value: root.phaseProgress
                indeterminate: root.state === "restarting" || root.unknownPhaseProgress
                active: root.visible && root.updating
            }
        }
        Text {
            Layout.fillWidth: true
            visible: root.state === "ready" || root.state === "updated" || root.state === "rolled_back"
            text: root.state === "ready" ? qsTr("Đã sẵn sàng. Khởi động lại khi các tác vụ hoàn tất để áp dụng bản cập nhật.")
                : root.state === "rolled_back" ? qsTr("Không thể mở phiên bản mới. HaizFlow đã khôi phục phiên bản trước.")
                : qsTr("Đã cập nhật HaizFlow.")
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.control
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
        }
        Text {
            Layout.fillWidth: true
            visible: root.controller.appUpdateError.length > 0 && root.state !== "error"
            text: root.updateError(root.controller.appUpdateError)
            color: Theme.danger
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.metadata
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
        }
        Text {
            Layout.fillWidth: true
            visible: root.controller.hasAppUpdate && root.controller.appUpdateBlocked
            text: qsTr("Chờ các tác vụ hoàn tất trước khi cập nhật.")
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.metadata
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space8
            StudioButton {
                objectName: "appUpdateCheckButton"
                text: qsTr("Kiểm tra lại")
                variant: "secondary"
                implicitHeight: 32
                enabled: !root.updating && root.state !== "checking" && root.state !== "ready"
                onClicked: root.controller.checkForAppUpdates()
            }
            Item { Layout.fillWidth: true }
            StudioButton {
                objectName: "appUpdateInstallButton"
                visible: root.controller.hasAppUpdate || root.state === "ready"
                text: root.state === "ready" ? qsTr("Khởi động lại") : qsTr("Cập nhật")
                variant: "primary"
                implicitHeight: 32
                enabled: !root.updating && root.state !== "checking" && !root.controller.appUpdateBlocked
                onClicked: root.confirmUpdate()
            }
        }
    }
}
