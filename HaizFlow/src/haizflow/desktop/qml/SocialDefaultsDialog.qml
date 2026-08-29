import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root

    title: qsTr("Nội dung mặc định")
    subtitle: qsTr("Áp dụng khi thêm video mới vào hàng đợi")
    preferredWidth: 560
    preferredHeight: 390
    maximumWidth: 600
    maximumHeight: 520

    function openForDefaults() {
        defaultCaption.text = AppController.tiktokDefaultCaption
        defaultHashtags.text = AppController.tiktokDefaultHashtags
        applyExisting.checked = true
        open()
    }

    SettingLabel {
        Layout.fillWidth: true
        text: qsTr("Nội dung")
    }

    AppTextArea {
        id: defaultCaption
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.minimumHeight: 110
        accessibleName: qsTr("Nội dung mặc định")
        placeholderText: qsTr("Viết nội dung bài đăng")
        selectByMouse: true
    }

    SettingLabel {
        Layout.fillWidth: true
        text: qsTr("Hashtag")
    }

    StudioField {
        id: defaultHashtags
        Layout.fillWidth: true
        accessibleName: qsTr("Hashtag mặc định")
        placeholderText: "#video #fyp"
        selectByMouse: true
    }

    StudioCheckBox {
        id: applyExisting
        text: qsTr("Áp dụng cho video đang chờ")
    }

    footerActions: [
        StudioButton {
            text: qsTr("Hủy")
            variant: "secondary"
            onClicked: root.close()
        },
        StudioButton {
            text: qsTr("Lưu")
            variant: "primary"
            onClicked: {
                if (AppController.saveTikTokPublishDefaults(
                        defaultCaption.text, defaultHashtags.text, applyExisting.checked))
                    root.close()
            }
        }
    ]
}
