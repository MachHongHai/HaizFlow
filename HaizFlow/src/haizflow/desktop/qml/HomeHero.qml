import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    implicitHeight: 142
    radius: Theme.radius
    color: Theme.surfaceElevated
    border.width: 1
    border.color: Theme.outline

    Rectangle {
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.margins: 1
        width: 3
        radius: 2
        color: Theme.interactive
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.space24
        anchors.rightMargin: Theme.space20
        anchors.topMargin: Theme.space16
        anchors.bottomMargin: Theme.space16
        spacing: Theme.space20

        ColumnLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            spacing: Theme.space8

            Text {
                Layout.fillWidth: true
                text: qsTr("Biên dịch video ngay trên máy")
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.display
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                maximumLineCount: 2
            }

            Text {
                Layout.fillWidth: true
                Layout.maximumWidth: 660
                text: qsTr("Tạo phụ đề, giọng đọc, bản phối và video hoàn chỉnh mà không cần API trả phí.")
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.body
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                lineHeight: 1.35
                maximumLineCount: 2
            }

            RowLayout {
                spacing: Theme.space16

                Text {
                    text: qsTr("Miễn phí")
                    color: Theme.interactiveHover
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.label
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }
                Text {
                    text: qsTr("Chạy cục bộ")
                    color: Theme.textSubtle
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.label
                    textFormat: Text.PlainText
                }
                Text {
                    text: qsTr("Nguồn mở")
                    color: Theme.textSubtle
                    font.family: Theme.fontFamily
                    font.pixelSize: TypeScale.label
                    textFormat: Text.PlainText
                }
            }
        }

        Image {
            Layout.preferredWidth: 82
            Layout.preferredHeight: 82
            source: Qt.resolvedUrl("../assets/branding/haizflow-mark.png")
            sourceSize.width: 164
            sourceSize.height: 164
            fillMode: Image.PreserveAspectFit
            asynchronous: true
            Accessible.name: qsTr("Biểu tượng HaizFlow")
        }
    }
}
