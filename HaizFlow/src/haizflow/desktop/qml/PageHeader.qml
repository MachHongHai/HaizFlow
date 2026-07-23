import QtQuick
import QtQuick.Layouts
import "."

RowLayout {
    id: root

    property string title: ""
    property string subtitle: ""
    default property alias actions: actionArea.data

    spacing: Theme.space24

    ColumnLayout {
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        spacing: Theme.space4

        Text {
            Layout.fillWidth: true
            text: root.title
            color: Theme.text
            font.pixelSize: Theme.h1
            font.weight: Font.DemiBold
            textFormat: Text.PlainText
            elide: Text.ElideRight
            maximumLineCount: 1
            wrapMode: Text.NoWrap
        }

        Text {
            Layout.fillWidth: true
            visible: root.subtitle.length > 0
            text: root.subtitle
            color: Theme.textMuted
            font.pixelSize: Theme.body
            textFormat: Text.PlainText
            elide: Text.ElideRight
            maximumLineCount: 1
            wrapMode: Text.NoWrap
        }
    }

    RowLayout {
        id: actionArea
        Layout.alignment: Qt.AlignVCenter
        spacing: Theme.space8
    }
}
