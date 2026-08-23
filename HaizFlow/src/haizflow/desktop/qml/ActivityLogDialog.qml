pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

FloatingToolDialog {
    id: root

    property string logText: ""
    property string detailText: ""

    expandedWidth: 1080
    expandedHeight: 760
    toolTitle: I18n.t("Activity log")
    toolSubtitle: root.detailText

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.space16
        spacing: Theme.space8

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space8

            Text {
                Layout.fillWidth: true
                text: I18n.t("Processing diagnostics")
                color: Theme.textMuted
                font.pixelSize: Theme.caption
                textFormat: Text.PlainText
                elide: Text.ElideRight
            }

            AppButton {
                text: I18n.t("Copy")
                iconGlyph: "\uE8C8"
                compact: true
                tone: "secondary"
                onClicked: activityLog.copyAll()
            }
        }

        LogViewer {
            id: activityLog
            Layout.fillWidth: true
            Layout.fillHeight: true
            text: root.logText
            emptyText: I18n.t("No logs loaded.")
        }
    }
}
