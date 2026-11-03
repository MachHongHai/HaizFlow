pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root
    objectName: "translationDataConsentDialog"
    property string choice: ""
    property string originalChoice: ""
    signal confirmed(string choice, string originalChoice)
    title: qsTr("Quyền riêng tư của model")
    preferredWidth: 520
    function openFor(value, original) {
        choice = value;
        originalChoice = original;
        open();
    }
    Text {
        Layout.fillWidth: true
        text: AppController.translationApi.choiceLabel(root.choice)
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.body
        font.weight: Font.Medium
        textFormat: Text.PlainText
        wrapMode: Text.Wrap
    }
    Text {
        Layout.fillWidth: true
        text: qsTr("Nhà cung cấp model này có thể lưu phụ đề và hướng dẫn dịch để đánh giá, cải thiện hoặc huấn luyện dịch vụ. Không dùng với nội dung nhạy cảm.")
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.body
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
    }
    Text {
        Layout.fillWidth: true
        text: qsTr("Quyền chỉ áp dụng cho kết nối và model này. Các model khác vẫn chặn thu thập dữ liệu.")
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.label
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
    }
    footerActions: [
        StudioButton {
            objectName: "translationDataConsentCancel"
            text: qsTr("Hủy")
            onClicked: root.close()
        },
        StudioButton {
            objectName: "translationDataConsentAllow"
            text: qsTr("Đồng ý và chọn")
            variant: "primary"
            onClicked: root.confirmed(root.choice, root.originalChoice)
        }
    ]
}
