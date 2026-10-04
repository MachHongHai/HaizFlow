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

    AutoSaveTextField {
        id: watermarkField
        Layout.fillWidth: true
        maximumLength: 80
        placeholderText: qsTr("Nhập nội dung watermark")
        accessibleName: qsTr("Nội dung watermark")
        selectByMouse: true
        onValueCommitted: function(value) { root.watermarkAccepted(value.trim()); }
        Keys.onReturnPressed: {
            commitEdits();
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
            text: qsTr("Đóng")
            variant: "ghost"
            onClicked: { watermarkField.commitEdits(); root.close(); }
        },
        StudioButton {
            text: qsTr("Lưu")
            variant: "primary"
            onClicked: {
                watermarkField.commitEdits();
                root.close();
            }
        }
    ]
}
