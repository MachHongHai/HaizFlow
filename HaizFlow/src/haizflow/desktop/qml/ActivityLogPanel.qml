pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    readonly property string detailText: AppController.hasSelectedVideo
        ? AppController.selectedFileName + "  ·  " + I18n.t(AppController.selectedStatus)
        : I18n.t("Live processing output")
    readonly property ActivityLogDialog expandedLogDialog: expandedLogLoader.item as ActivityLogDialog

    function openExpandedLog() {
        if (expandedLogLoader.status === Loader.Ready) {
            if (root.expandedLogDialog)
                root.expandedLogDialog.open()
            return
        }
        expandedLogLoader.active = true
    }

    color: Theme.surfaceElevated
    radius: Theme.radius
    border.width: 1
    border.color: Theme.outline

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.space12
        spacing: Theme.space8

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space8

            Rectangle {
                Layout.preferredWidth: 30
                Layout.preferredHeight: 30
                radius: Theme.radiusSmall
                color: Theme.blueMuted

                AppIcon {
                    anchors.centerIn: parent
                    width: 18
                    height: 18
                    glyph: "\uE756"
                    iconColor: Theme.blue
                    iconSize: Theme.iconSmall
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                spacing: 1

                Text {
                    Layout.fillWidth: true
                    text: I18n.t("Activity log")
                    color: Theme.text
                    font.pixelSize: Theme.body
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }

                Text {
                    Layout.fillWidth: true
                    text: root.detailText
                    color: Theme.textSubtle
                    font.pixelSize: Theme.label
                    textFormat: Text.PlainText
                    elide: Text.ElideMiddle
                }
            }

            AppButton {
                text: I18n.t("Expand log")
                tone: "ghost"
                compact: true
                activeFocusOnTab: true
                onClicked: root.openExpandedLog()
            }
        }

        LogViewer {
            Layout.fillWidth: true
            Layout.fillHeight: true
            compact: true
            text: expandedLogLoader.active ? "" : AppController.logs
            emptyText: I18n.t("Logs will appear here while this project is processing.")
        }
    }

    Loader {
        id: expandedLogLoader

        active: false
        asynchronous: false
        onLoaded: {
            if (status === Loader.Ready && root.expandedLogDialog)
                root.expandedLogDialog.open()
        }

        sourceComponent: Component {
            ActivityLogDialog {
                logText: AppController.logs
                detailText: root.detailText
                onClosed: expandedLogLoader.active = false
            }
        }
    }
}
