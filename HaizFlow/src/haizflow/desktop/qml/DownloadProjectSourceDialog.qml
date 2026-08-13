pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Dialog {
    id: root

    property string importMode: "single"
    readonly property bool multipleSelection: importMode === "batch"

    modal: true
    focus: true
    parent: Overlay.overlay
    width: Math.min(760, parent ? parent.width - 48 : 760)
    height: Math.min(620, parent ? parent.height - 48 : 620)
    x: Math.round((parent.width - width) / 2)
    y: Math.round((parent.height - height) / 2)
    padding: 0
    header: null
    footer: null
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    function openForMode(mode) {
        importMode = mode === "batch" ? "batch" : "single"
        AppController.refreshDownloadProjectSources()
        open()
    }

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
            Layout.preferredHeight: 68
            Layout.leftMargin: Theme.space24
            Layout.rightMargin: Theme.space16
            spacing: Theme.space12

            ColumnLayout {
                Layout.fillWidth: true
                spacing: Theme.space4

                Text {
                    Layout.fillWidth: true
                    text: I18n.t("Import from download projects")
                    color: Theme.text
                    font.pixelSize: Theme.h2
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }

                Text {
                    Layout.fillWidth: true
                    text: root.multipleSelection
                        ? I18n.t("Choose downloaded videos to add to this batch")
                        : I18n.t("Choose one downloaded video")
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
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

        ListView {
            id: sourceList

            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: Theme.space16
            model: AppController.downloadProjectSourceModel
            spacing: Theme.space8
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            reuseItems: true

            delegate: Rectangle {
                id: sourceDelegate

                required property int index
                required property string downloadItemId
                required property string downloadProjectName
                required property string downloadCategory
                required property string downloadFileName
                required property string downloadFilePath
                required property real downloadFileSize
                required property bool downloadSelected

                width: ListView.view.width
                height: 70
                radius: Theme.radiusSmall
                color: downloadSelected ? Theme.interactiveMuted : Theme.surfaceMuted
                border.width: 1
                border.color: downloadSelected ? Theme.focus : Theme.outline

                ListView.onPooled: {
                    visible = false
                    focus = false
                }
                ListView.onReused: {
                    visible = true
                    focus = false
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.space12
                    spacing: Theme.space12

                    Rectangle {
                        Layout.preferredWidth: 38
                        Layout.preferredHeight: 38
                        radius: Theme.radiusSmall
                        color: Theme.blueMuted

                        AppIcon {
                            anchors.centerIn: parent
                            width: 18
                            height: 18
                            glyph: "\uE714"
                            iconColor: Theme.blue
                            iconSize: Theme.iconSmall
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space4

                        Text {
                            Layout.fillWidth: true
                            text: sourceDelegate.downloadFileName
                            color: Theme.text
                            font.pixelSize: Theme.body
                            font.weight: Font.DemiBold
                            textFormat: Text.PlainText
                            elide: Text.ElideMiddle
                        }

                        Text {
                            Layout.fillWidth: true
                            text: sourceDelegate.downloadProjectName + " · "
                                + (sourceDelegate.downloadCategory === "channel"
                                    ? I18n.t("Channel") : I18n.t("Video"))
                            color: Theme.textMuted
                            font.pixelSize: Theme.caption
                            textFormat: Text.PlainText
                            elide: Text.ElideRight
                        }
                    }

                    Text {
                        text: sourceDelegate.downloadFileSize > 0
                            ? qsTr("%1 MB").arg((sourceDelegate.downloadFileSize / 1048576).toFixed(1))
                            : ""
                        color: Theme.textSubtle
                        font.pixelSize: Theme.label
                        textFormat: Text.PlainText
                    }

                    AppCheckBox {
                        checked: sourceDelegate.downloadSelected
                        onToggled: AppController.setDownloadProjectSourceSelected(
                            sourceDelegate.index,
                            checked,
                            !root.multipleSelection
                        )
                    }
                }
            }

            Text {
                anchors.centerIn: parent
                visible: sourceList.count === 0
                width: Math.min(420, sourceList.width - Theme.space32)
                text: I18n.t("No downloaded videos are available")
                color: Theme.textMuted
                font.pixelSize: Theme.body
                textFormat: Text.PlainText
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
            }

            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.divider
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 68
            Layout.leftMargin: Theme.space24
            Layout.rightMargin: Theme.space24
            spacing: Theme.space8

            Text {
                Layout.fillWidth: true
                text: qsTr("%1 %2")
                    .arg(AppController.downloadProjectSourceSelectedCount)
                    .arg(I18n.t("selected"))
                color: Theme.textMuted
                font.pixelSize: Theme.caption
                textFormat: Text.PlainText
            }

            AppButton {
                text: I18n.t("Cancel")
                tone: "ghost"
                onClicked: root.close()
            }

            AppButton {
                text: I18n.t("Import")
                tone: "primary"
                enabled: AppController.downloadProjectSourceSelectedCount > 0
                    && (root.multipleSelection
                        || AppController.downloadProjectSourceSelectedCount === 1)
                onClicked: {
                    if (AppController.importSelectedDownloadProjectVideos(root.importMode))
                        root.close()
                }
            }
        }
    }
}
