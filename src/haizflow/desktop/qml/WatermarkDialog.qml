pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root

    property string initialText: ""
    signal watermarkAccepted(string text)

    preferredWidth: 460
    maximumWidth: 500
    title: qsTr("Watermark chữ")

    function openWithText(text) {
        initialText = text || ""
        open()
    }

    function applyWatermark() {
        root.watermarkAccepted(watermarkField.text.trim())
        root.close()
    }

    onOpened: {
        watermarkField.text = initialText
        watermarkField.forceActiveFocus()
        watermarkField.selectAll()
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
        Keys.onReturnPressed: root.applyWatermark()
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
            text: qsTr("Áp dụng")
            variant: "primary"
            onClicked: root.applyWatermark()
        }
    ]
}
