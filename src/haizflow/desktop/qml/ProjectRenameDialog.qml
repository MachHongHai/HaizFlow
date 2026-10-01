pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root
    property var controller: AppController
    property string projectKey: ""
    property string originalName: ""
    title: qsTr("Đổi tên dự án")
    preferredWidth: 480

    function openForProject(key, name) {
        projectKey = key;
        originalName = name;
        nameField.text = name;
        open();
    }
    function submit() {
        if (nameField.text.trim().length > 0 && controller.renameProject(projectKey, nameField.text.trim()))
            close();
    }
    onOpened: {
        nameField.forceActiveFocus();
        nameField.selectAll();
    }
    StudioField {
        id: nameField
        objectName: "renameProjectName"
        Layout.fillWidth: true
        accessibleName: qsTr("Tên dự án")
        maximumLength: 120
        Keys.onReturnPressed: root.submit()
    }
    Text {
        Layout.fillWidth: true
        text: qsTr("Chỉ đổi tên hiển thị. Thư mục, dữ liệu và liên kết của dự án được giữ nguyên.")
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.metadata
    }
    footerActions: [
        StudioButton { text: qsTr("Hủy"); variant: "ghost"; onClicked: root.close() },
        StudioButton {
            text: qsTr("Lưu tên")
            variant: "primary"
            enabled: nameField.text.trim().length > 0 && nameField.text.trim() !== root.originalName
            onClicked: root.submit()
        }
    ]
}
