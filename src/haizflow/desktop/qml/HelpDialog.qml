pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root

    title: qsTr("Trợ giúp")
    preferredWidth: 560
    maximumWidth: 600

    SettingRow {
        Layout.fillWidth: true
        label: qsTr("Tạo dự án")
        description: qsTr("Mở menu Dự án, sau đó chọn loại dự án.")
    }

    SettingRow {
        Layout.fillWidth: true
        label: qsTr("Tự động")
        description: qsTr("Xử lý video bằng cấu hình đã chọn.")
    }

    SettingRow {
        Layout.fillWidth: true
        label: qsTr("Thủ công")
        description: qsTr("Chạy từng công cụ và chỉnh trực tiếp trong editor.")
    }

    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: 1
        color: Theme.divider
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space16

        ExternalTextLink {
            text: qsTr("Mở hướng dẫn trên GitHub")
            destination: "https://github.com/MachHongHai/HaizFlow"
        }
        ExternalTextLink {
            text: qsTr("Báo lỗi")
            destination: "https://github.com/MachHongHai/HaizFlow/issues"
        }
        Item { Layout.fillWidth: true }
    }

    footerActions: StudioButton {
        text: qsTr("Đóng")
        variant: "primary"
        onClicked: root.close()
    }
}
