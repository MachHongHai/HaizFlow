pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root

    signal saveRequested(int row, string caption, string hashtags)

    property int row: -1
    property string fileName: ""
    property string initialCaption: ""
    property string initialHashtags: ""
    readonly property int postLength: captionInput.text.length
        + (captionInput.text.length > 0 && hashtagInput.text.trim().length > 0 ? 1 : 0)
        + hashtagInput.text.trim().length

    preferredWidth: 620
    maximumWidth: 680
    title: qsTr("Chỉnh nội dung bài đăng")
    subtitle: root.fileName

    function openForItem(itemRow, name, caption, hashtags) {
        row = itemRow
        fileName = name
        initialCaption = caption
        initialHashtags = hashtags
        captionInput.text = caption
        hashtagInput.text = hashtags
        open()
    }

    function savePost() {
        if (root.postLength > 2200)
            return
        root.saveRequested(root.row, captionInput.text, hashtagInput.text)
        root.close()
    }

    onOpened: captionInput.forceActiveFocus()

    RowLayout {
        Layout.fillWidth: true

        SettingLabel {
            Layout.fillWidth: true
            text: qsTr("Nội dung")
        }

        Text {
            text: qsTr("%1 / 2200").arg(root.postLength)
            color: root.postLength > 2200 ? Theme.danger : Theme.textSubtle
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.metadata
            textFormat: Text.PlainText
        }
    }

    AppTextArea {
        id: captionInput
        Layout.fillWidth: true
        Layout.preferredHeight: 156
        placeholderText: qsTr("Viết nội dung cho video")
        accessibleName: qsTr("Nội dung bài đăng")
        selectByMouse: true
    }

    SettingLabel {
        Layout.fillWidth: true
        text: qsTr("Hashtag")
        helpText: qsTr("Ngăn cách bằng dấu cách hoặc dấu phẩy. Hashtag trùng sẽ được loại bỏ.")
    }

    StudioField {
        id: hashtagInput
        Layout.fillWidth: true
        placeholderText: qsTr("Ví dụ: #review #video #fyp")
        accessibleName: qsTr("Hashtag")
        selectByMouse: true
        Keys.onReturnPressed: root.savePost()
    }

    InlineBanner {
        Layout.fillWidth: true
        visible: root.postLength > 2200
        tone: "danger"
        message: qsTr("Nội dung vượt quá 2.200 ký tự.")
    }

    footerActions: [
        StudioButton {
            text: qsTr("Hủy")
            variant: "ghost"
            onClicked: root.close()
        },
        StudioButton {
            text: qsTr("Lưu")
            variant: "primary"
            enabled: root.postLength <= 2200
            onClicked: root.savePost()
        }
    ]
}
