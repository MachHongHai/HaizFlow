pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root

    title: qsTr("Trợ giúp")
    subtitle: qsTr("Các thao tác chính")
    preferredWidth: 560
    maximumWidth: 600

    SettingRow {
        Layout.fillWidth: true
        label: qsTr("Dự án mới")
        description: qsTr("Mở menu Dự án và chọn loại dự án cần tạo.")
    }

    SettingRow {
        Layout.fillWidth: true
        label: qsTr("Tự động")
        description: qsTr("Chạy nhận dạng, dịch, tạo giọng và xuất video trong một lần.")
    }

    SettingRow {
        Layout.fillWidth: true
        label: qsTr("Thủ công")
        description: qsTr("Chạy riêng từng công cụ và chỉnh trực tiếp trên khung xem trước.")
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

    footerActions: AppButton {
        text: qsTr("Đóng")
        tone: "primary"
        onClicked: root.close()
    }
}
