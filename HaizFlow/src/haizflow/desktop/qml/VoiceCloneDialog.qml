import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

FloatingToolDialog {
    id: root

    expandedWidth: 620
    expandedHeight: 430
    toolTitle: I18n.t("Clone my voice")
    toolSubtitle: I18n.t("Use only a sample you own or have permission to use")

    property string samplePath: ""

    function openForSelectedVideo() {
        samplePath = AppController.voiceCloneReferencePath
        transcript.text = AppController.voiceCloneReferenceTranscript
        open()
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.space20
        spacing: Theme.space16

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 78
            radius: Theme.radiusSmall
            color: Theme.surfaceElevated
            border.width: 1
            border.color: Theme.outline

            RowLayout {
                anchors.fill: parent
                anchors.margins: Theme.space12
                spacing: Theme.space12

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3
                    Text {
                        text: I18n.t("Voice sample")
                        color: Theme.text
                        font.pixelSize: Theme.body
                        font.weight: Font.DemiBold
                    }
                    Text {
                        Layout.fillWidth: true
                        text: root.samplePath || I18n.t("No sample selected")
                        color: root.samplePath ? Theme.textMuted : Theme.textSubtle
                        font.pixelSize: Theme.caption
                        elide: Text.ElideMiddle
                    }
                }

                AppButton {
                    text: I18n.t("Choose sample")
                    compact: true
                    onClicked: {
                        const selected = AppController.chooseVoiceCloneReference()
                        if (selected.length > 0)
                            root.samplePath = selected
                    }
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Theme.space4

            Text {
                text: I18n.t("Exact sample transcript")
                color: Theme.textMuted
                font.pixelSize: Theme.caption
                font.weight: Font.Medium
            }

            TextArea {
                id: transcript
                Layout.fillWidth: true
                Layout.fillHeight: true
                placeholderText: I18n.t("Type exactly what is spoken in the sample")
                wrapMode: TextEdit.Wrap
                selectByMouse: true
                color: Theme.text
                font.pixelSize: Theme.body
                background: Rectangle {
                    color: Theme.input
                    radius: Theme.radiusSmall
                    border.width: transcript.activeFocus ? 2 : 1
                    border.color: transcript.activeFocus ? Theme.focus : Theme.outline
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space8

            AppButton {
                visible: AppController.voiceCloneReferencePath.length > 0
                text: I18n.t("Remove sample")
                tone: "danger"
                compact: true
                onClicked: {
                    if (AppController.clearVoiceCloneReference()) {
                        root.samplePath = ""
                        transcript.clear()
                    }
                }
            }

            Item { Layout.fillWidth: true }

            AppButton {
                text: I18n.t("Save voice")
                tone: "primary"
                enabled: root.samplePath.length > 0 && transcript.text.trim().length > 0
                onClicked: {
                    if (AppController.setVoiceCloneReference(root.samplePath, transcript.text))
                        root.close()
                }
            }
        }
    }
}
