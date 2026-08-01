import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Dialog {
    id: root

    property string initialText: ""
    signal watermarkAccepted(string text)

    function openWithText(text) {
        initialText = text || ""
        open()
    }

    modal: true
    focus: true
    title: I18n.t("Text watermark")
    parent: Overlay.overlay
    width: Math.min(500, parent ? parent.width - 48 : 500)
    padding: Theme.space24
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    x: Math.round((parent.width - width) / 2)
    y: Math.round((parent.height - height) / 2)

    onOpened: {
        watermarkField.text = initialText
        watermarkField.forceActiveFocus()
        watermarkField.selectAll()
    }

    contentItem: ColumnLayout {
        spacing: Theme.space16

        Text {
            Layout.fillWidth: true
            text: I18n.t("A small, subtle text mark moves continuously across the exported video.")
            color: Theme.textMuted
            font.pixelSize: Theme.body
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
        }

        TextField {
            id: watermarkField
            Layout.fillWidth: true
            implicitHeight: 46
            maximumLength: 80
            placeholderText: I18n.t("Enter watermark text")
            selectByMouse: true
            activeFocusOnTab: true
            Accessible.name: I18n.t("Watermark text")
            background: Rectangle {
                radius: Theme.radiusSmall
                color: Theme.input
                border.width: watermarkField.activeFocus ? 2 : 1
                border.color: watermarkField.activeFocus ? Theme.focus : Theme.outline
            }
            Keys.onReturnPressed: {
                root.watermarkAccepted(text.trim())
                root.close()
            }
        }

        Text {
            Layout.fillWidth: true
            text: qsTr("%1/80").arg(watermarkField.text.length)
            color: Theme.textSubtle
            font.pixelSize: Theme.caption
            horizontalAlignment: Text.AlignRight
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: Theme.space4

            Item { Layout.fillWidth: true }

            AppButton {
                text: I18n.t("Cancel")
                tone: "secondary"
                onClicked: root.close()
            }

            AppButton {
                text: I18n.t("Apply")
                tone: "primary"
                onClicked: {
                    root.watermarkAccepted(watermarkField.text.trim())
                    root.close()
                }
            }
        }
    }
}
