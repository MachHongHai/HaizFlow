pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root

    property string initialText: ""
    signal watermarkAccepted(string text)

    preferredWidth: 460
    maximumWidth: 520
    title: qsTr("Watermark chữ")

    function openWithText(text) {
        initialText = text || "";
        open();
    }

    onOpened: {
        watermarkField.text = initialText;
        watermarkField.forceActiveFocus();
        watermarkField.selectAll();
    }

    SettingLabel {
        Layout.fillWidth: true
        text: qsTr("Nội dung watermark")
    }

    StudioField {
        id: watermarkField
        Layout.fillWidth: true
        maximumLength: 80
        placeholderText: qsTr("Nhập nội dung watermark")
        accessibleName: qsTr("Nội dung watermark")
        selectByMouse: true
        Keys.onReturnPressed: {
            root.watermarkAccepted(text.trim());
            root.close();
        }
    }

    Text {
        Layout.fillWidth: true
        text: qsTr("%1/80").arg(watermarkField.text.length)
        color: Theme.textSubtle
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.metadata
        horizontalAlignment: Text.AlignRight
        textFormat: Text.PlainText
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
            onClicked: {
                root.watermarkAccepted(watermarkField.text.trim());
                root.close();
            }
        }
    ]
}
