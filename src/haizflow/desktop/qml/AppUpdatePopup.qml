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
    readonly property bool updating: ["downloading", "verifying", "installing"].indexOf(state) >= 0
    parent: Overlay.overlay
    width: Math.min(380, parent ? parent.width - Theme.space16 : 380)
    padding: Theme.space16
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    function updateError(source) {
        const messages = {
            "Dừng hoặc chờ các tác vụ hoàn tất trước khi cập nhật.": qsTr("Dừng hoặc chờ các tác vụ hoàn tất trước khi cập nhật."),
            "Cập nhật trực tiếp chỉ dùng trong bản HaizFlow đã cài đặt.": qsTr("Cập nhật trực tiếp chỉ dùng trong bản HaizFlow đã cài đặt."),
            "Bản phát hành chưa có bộ cài Windows kèm mã kiểm tra. Hãy xem chi tiết cập nhật.": qsTr("Bản phát hành chưa có bộ cài Windows kèm mã kiểm tra. Hãy xem chi tiết cập nhật."),
            "Bộ cài chưa có chữ ký hợp lệ. Không thể cập nhật tự động.": qsTr("Bộ cài chưa có chữ ký hợp lệ. Không thể cập nhật tự động."),
            "Bộ cài tải xuống chưa đầy đủ hoặc mã kiểm tra không khớp. Hãy thử lại.": qsTr("Bộ cài tải xuống chưa đầy đủ hoặc mã kiểm tra không khớp. Hãy thử lại."),
            "Bộ cài đã đóng. Nếu cập nhật thành công, hãy khởi động lại HaizFlow.": qsTr("Bộ cài đã đóng. Nếu cập nhật thành công, hãy khởi động lại HaizFlow.")
        };
        return messages[source] || qsTr("Không thể cập nhật. Hãy thử lại hoặc xem chi tiết trên trang HaizFlow.");
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
                    : root.controller.hasAppUpdate
                        ? qsTr("Đã có phiên bản mới, hãy cập nhật ngay, chi tiết bản cập nhật xem tại:")
                        : qsTr("Hiện tại chưa có phiên bản mới, chi tiết bản cập nhật gần nhất:")
            text: message + (root.state === "checking" || root.state === "idle" || root.state === "error"
                ? "" : ' <a href="https://haizflow.pages.dev/" style="color: '
                    + Theme.interactive + ';">haizflow.pages.dev</a>')
            color: Theme.textMuted
            linkColor: Theme.interactive
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.control
            textFormat: Text.RichText
            wrapMode: Text.WordWrap
            activeFocusOnTab: true
            Accessible.role: Accessible.Link
            Accessible.name: message + " haizflow.pages.dev"
            onLinkActivated: link => {
                if (link === "https://haizflow.pages.dev/")
                    Qt.openUrlExternally(link);
            }
            Keys.onReturnPressed: {
                if (root.state !== "checking" && root.state !== "idle" && root.state !== "error")
                    Qt.openUrlExternally("https://haizflow.pages.dev/");
            }
            HoverHandler {
                cursorShape: updateMessage.hoveredLink ? Qt.PointingHandCursor : Qt.ArrowCursor
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            visible: root.updating
            spacing: Theme.space4
            Text {
                Layout.fillWidth: true
                text: root.state === "downloading"
                    ? qsTr("Đang tải bộ cài · %1%").arg(root.controller.appUpdateDownloadProgress)
                    : root.state === "verifying" ? qsTr("Đang kiểm tra bộ cài…")
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
                value: root.controller.appUpdateDownloadProgress
                indeterminate: root.state === "verifying"
                active: root.visible && root.updating
            }
        }
        Text {
            Layout.fillWidth: true
            visible: root.controller.appUpdateError.length > 0 && root.state !== "error"
            text: root.updateError(root.controller.appUpdateError)
            color: Theme.textMuted
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
                enabled: !root.updating && root.state !== "checking"
                onClicked: root.controller.checkForAppUpdates()
            }
            Item { Layout.fillWidth: true }
            StudioButton {
                objectName: "appUpdateInstallButton"
                visible: root.controller.hasAppUpdate
                text: qsTr("Cập nhật")
                variant: "primary"
                implicitHeight: 32
                enabled: !root.updating && root.state !== "checking" && !root.controller.appUpdateBlocked
                onClicked: root.controller.installAppUpdate()
            }
        }
    }
}
