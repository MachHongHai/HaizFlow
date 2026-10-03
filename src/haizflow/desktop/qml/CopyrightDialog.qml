pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

AppDialog {
    id: root
    title: qsTr("Bản quyền")
    subtitle: "HaizFlow"
    preferredWidth: 650
    preferredHeight: 520
    maximumWidth: 680
    maximumHeight: 620

    ScrollView {
        id: scroll
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.minimumHeight: 0
        contentWidth: availableWidth
        contentHeight: content.implicitHeight
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ColumnLayout {
            id: content
            width: scroll.availableWidth
            spacing: Theme.space16
            Text {
                Layout.fillWidth: true
                text: qsTr("© 2026 Mạch Hồng Hải\nTác giả và chủ sở hữu HaizFlow.")
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.body
                color: Theme.text
                wrapMode: Text.WordWrap
                textFormat: Text.PlainText
                lineHeight: 1.4
            }
            Text {
                Layout.fillWidth: true
                text: qsTr("HaizFlow được sử dụng miễn phí. Mã nguồn được cung cấp để nghiên cứu và chỉnh sửa cá nhân hoặc nội bộ. Không được phân phối lại, đóng gói lại, bán, cho thuê hoặc mạo nhận phần mềm khi chưa có chấp thuận bằng văn bản của chủ sở hữu. Phạm vi quyền và ngoại lệ được quy định trong giấy phép.")
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.control
                color: Theme.textMuted
                wrapMode: Text.WordWrap
                textFormat: Text.PlainText
                lineHeight: 1.4
            }
            AboutLinkRow {
                label: qsTr("Giấy phép")
                value: "HaizFlow Source-Available 1.0"
                destination: "https://github.com/MachHongHai/HaizFlow/blob/main/LICENSE"
                copyValue: destination
            }
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                color: Theme.divider
            }
            Text {
                Layout.fillWidth: true
                text: qsTr("Thư viện, mô hình và tài nguyên đi kèm tuân theo giấy phép riêng. Người dùng có trách nhiệm bảo đảm quyền sử dụng video, âm nhạc và mẫu giọng nói.")
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.control
                color: Theme.textMuted
                wrapMode: Text.WordWrap
                textFormat: Text.PlainText
                lineHeight: 1.4
            }
            AboutLinkRow {
                label: qsTr("Thành phần")
                value: qsTr("Giấy phép và thông báo")
                destination: "https://github.com/MachHongHai/HaizFlow/blob/main/THIRD_PARTY_NOTICES.md"
                copyValue: destination
            }
        }
    }
    footerActions: StudioButton {
        text: qsTr("Đóng")
        variant: "primary"
        onClicked: root.close()
    }
}
