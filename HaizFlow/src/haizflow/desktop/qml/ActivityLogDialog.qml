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
    toolTitle: qsTr("Nhật ký kỹ thuật")
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
                text: qsTr("Chi tiết xử lý")
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.metadata
                textFormat: Text.PlainText
                elide: Text.ElideRight
            }

            AppButton {
                text: qsTr("Sao chép")
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
            emptyText: qsTr("Chưa có dữ liệu.")
        }
    }
}
