pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Dialog {
    id: root

    property string logText: ""
    property string detailText: ""

    modal: true
    focus: true
    parent: Overlay.overlay
    width: Math.min(1080, parent ? parent.width - 72 : 1080)
    height: Math.min(760, parent ? parent.height - 72 : 760)
    padding: 0
    closePolicy: Popup.CloseOnEscape
    x: Math.round((parent.width - width) / 2)
    y: Math.round((parent.height - height) / 2)
    header: null
    footer: null

    background: Rectangle {
        color: Theme.surface
        radius: Theme.radius
        border.width: 1
        border.color: Theme.outlineStrong
    }

    contentItem: ColumnLayout {
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 68
            Layout.leftMargin: Theme.space20
            Layout.rightMargin: Theme.space12
            spacing: Theme.space12

            Rectangle {
                Layout.preferredWidth: 34
                Layout.preferredHeight: 34
                radius: Theme.radiusSmall
                color: Theme.blueMuted

                AppIcon {
                    anchors.centerIn: parent
                    width: 20
                    height: 20
                    glyph: "\uE756"
                    iconColor: Theme.blue
                    iconSize: Theme.icon
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                spacing: 2

                Text {
                    Layout.fillWidth: true
                    text: I18n.t("Activity log")
                    color: Theme.text
                    font.pixelSize: Theme.h3
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }

                Text {
                    Layout.fillWidth: true
                    text: root.detailText
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

        LogViewer {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: Theme.space16
            text: root.logText
            emptyText: I18n.t("No logs loaded.")
        }
    }
}
