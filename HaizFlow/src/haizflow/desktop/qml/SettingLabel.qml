pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

RowLayout {
    id: root

    property string text: ""
    property string helpText: ""
    property bool labelVisible: true

    spacing: Theme.space4

    Text {
        visible: root.labelVisible
        Layout.fillWidth: true
        text: root.text
        color: Theme.textMuted
        font.pixelSize: Theme.caption
        textFormat: Text.PlainText
    }

    Button {
        id: helpButton
        visible: root.helpText.length > 0
        Layout.preferredWidth: 20
        Layout.preferredHeight: 20
        padding: 0
        focusPolicy: Qt.TabFocus
        Accessible.name: I18n.t("Help for %1").arg(root.text)
        onClicked: helpDialog.open()

        contentItem: Text {
            text: "?"
            color: helpButton.hovered || helpButton.activeFocus ? Theme.focus : Theme.textSubtle
            font.pixelSize: Theme.label
            font.weight: Font.DemiBold
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }

        background: Rectangle {
            radius: width / 2
            color: helpButton.hovered ? Theme.interactiveMuted : "transparent"
            border.width: 1
            border.color: helpButton.activeFocus ? Theme.focus : Theme.outlineStrong
        }
    }

    Item {
        // Keep the popup out of RowLayout's managed visual children. The
        // dialog reparents itself to Overlay.overlay when shown.
        Layout.preferredWidth: 0
        Layout.preferredHeight: 0

        Dialog {
            id: helpDialog
            modal: true
            focus: true
            parent: Overlay.overlay
            width: Math.min(440, parent ? parent.width - 48 : 440)
            padding: 0
            closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
            x: Math.round((parent.width - width) / 2)
            y: Math.round((parent.height - implicitHeight) / 2)
            header: null
            footer: null

            background: Rectangle {
                radius: Theme.radius
                color: Theme.surface
                border.width: 1
                border.color: Theme.outlineStrong
            }

            contentItem: ColumnLayout {
                spacing: 0

                RowLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: Theme.space20
                    Layout.rightMargin: Theme.space8
                    Layout.topMargin: Theme.space12
                    Layout.bottomMargin: Theme.space8

                    Text {
                        Layout.fillWidth: true
                        text: root.text
                        color: Theme.text
                        font.pixelSize: Theme.h3
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                    }

                    IconButton {
                        glyph: "\uE711"
                        controlSize: 32
                        toolTipText: I18n.t("Close")
                        onClicked: helpDialog.close()
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    color: Theme.divider
                }

                Text {
                    Layout.fillWidth: true
                    Layout.margins: Theme.space20
                    text: root.helpText
                    color: Theme.textMuted
                    font.pixelSize: Theme.body
                    lineHeight: 1.25
                    wrapMode: Text.WordWrap
                    textFormat: Text.PlainText
                }
            }
        }
    }
}
