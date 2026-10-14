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
    toolTitle: qsTr("Log kỹ thuật")
    toolSubtitle: root.detailText

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.space16
        spacing: Theme.space12

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space8

            SearchField {
                id: logSearch
                Layout.fillWidth: true
                Layout.maximumWidth: 520
                placeholderText: qsTr("Tìm trong log")
                Accessible.name: qsTr("Tìm trong log")
            }

            AppComboBox {
                id: severityBox
                Layout.preferredWidth: 150
                model: [qsTr("Tất cả mức"), "Info", "Warning", "Error", "Debug"]
            }

            StudioButton {
                text: qsTr("Sao chép toàn bộ")
                iconGlyph: "\uE8C8"
                variant: "secondary"
                onClicked: activityLog.copyAll()
            }
        }

        LogViewer {
            id: activityLog
            Layout.fillWidth: true
            Layout.fillHeight: true
            text: root.logText
            query: logSearch.text
            levelFilter: ["all", "INFO", "WARN", "ERROR", "DEBUG"][severityBox.currentIndex]
            emptyText: qsTr("Không có dòng log phù hợp.")
        }

        Text {
            Layout.fillWidth: true
            text: qsTr("%1 / %2 dòng").arg(activityLog.filteredLineCount).arg(activityLog.lineCount)
            color: Theme.textSubtle
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.metadata
            textFormat: Text.PlainText
        }
    }
}
