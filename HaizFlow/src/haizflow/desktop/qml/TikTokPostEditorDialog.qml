import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Dialog {
    id: root

    signal saveRequested(int row, string caption, string hashtags)

    property int row: -1
    property string fileName: ""
    property string initialCaption: ""
    property string initialHashtags: ""
    readonly property int postLength: captionInput.text.length
        + (captionInput.text.length > 0 && hashtagInput.text.trim().length > 0 ? 1 : 0)
        + hashtagInput.text.trim().length

    modal: true
    focus: true
    parent: Overlay.overlay
    width: Math.min(680, parent ? parent.width - 48 : 680)
    height: Math.min(510, parent ? parent.height - 48 : 510)
    x: Math.round((parent.width - width) / 2)
    y: Math.round((parent.height - height) / 2)
    padding: 0
    header: null
    footer: null
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    function openForItem(itemRow, name, caption, hashtags) {
        row = itemRow
        fileName = name
        initialCaption = caption
        initialHashtags = hashtags
        captionInput.text = caption
        hashtagInput.text = hashtags
        open()
    }

    onOpened: captionInput.forceActiveFocus()

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
            Layout.preferredHeight: 66
            Layout.leftMargin: Theme.space24
            Layout.rightMargin: Theme.space16
            spacing: Theme.space12

            ColumnLayout {
                Layout.fillWidth: true
                spacing: Theme.space4

                Text {
                    Layout.fillWidth: true
                    text: I18n.t("Edit TikTok post")
                    color: Theme.text
                    font.pixelSize: Theme.h2
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }

                Text {
                    Layout.fillWidth: true
                    text: root.fileName
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    textFormat: Text.PlainText
                    elide: Text.ElideMiddle
                }
            }

            IconButton {
                glyph: "\uE711"
                toolTipText: I18n.t("Close")
                onClicked: root.close()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.divider
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: Theme.space24
            spacing: Theme.space12

            RowLayout {
                Layout.fillWidth: true

                Text {
                    text: I18n.t("Caption")
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    font.weight: Font.Medium
                    textFormat: Text.PlainText
                }

                Item { Layout.fillWidth: true }

                Text {
                    text: qsTr("%1 / 2200").arg(root.postLength)
                    color: root.postLength > 2200 ? Theme.danger : Theme.textSubtle
                    font.pixelSize: Theme.label
                    textFormat: Text.PlainText
                }
            }

            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: 170
                clip: true

                TextArea {
                    id: captionInput
                    color: Theme.text
                    placeholderText: I18n.t("Write a caption for this video")
                    font.pixelSize: Theme.body
                    selectByMouse: true
                    wrapMode: TextEdit.Wrap
                    leftPadding: Theme.space12
                    rightPadding: Theme.space12
                    topPadding: Theme.space12
                    bottomPadding: Theme.space12
                    background: Rectangle {
                        radius: Theme.radiusSmall
                        color: Theme.input
                        border.width: captionInput.activeFocus ? 2 : 1
                        border.color: captionInput.activeFocus ? Theme.focus : Theme.outline
                    }
                }
            }

            Text {
                text: I18n.t("Hashtags")
                color: Theme.textMuted
                font.pixelSize: Theme.caption
                font.weight: Font.Medium
                textFormat: Text.PlainText
            }

            TextField {
                id: hashtagInput
                Layout.fillWidth: true
                implicitHeight: 44
                color: Theme.text
                placeholderText: I18n.t("Example: #review #video #fyp")
                font.pixelSize: Theme.body
                selectByMouse: true
                background: Rectangle {
                    radius: Theme.radiusSmall
                    color: Theme.input
                    border.width: hashtagInput.activeFocus ? 2 : 1
                    border.color: hashtagInput.activeFocus ? Theme.focus : Theme.outline
                }
            }

            Text {
                Layout.fillWidth: true
                text: I18n.t("Separate hashtags with spaces or commas. Duplicates are removed automatically.")
                color: Theme.textSubtle
                font.pixelSize: Theme.label
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space8

                Item { Layout.fillWidth: true }

                AppButton {
                    text: I18n.t("Cancel")
                    tone: "ghost"
                    onClicked: root.close()
                }

                AppButton {
                    text: I18n.t("Save")
                    tone: "primary"
                    enabled: root.postLength <= 2200
                    onClicked: {
                        root.saveRequested(root.row, captionInput.text, hashtagInput.text)
                        root.close()
                    }
                }
            }
        }
    }
}
