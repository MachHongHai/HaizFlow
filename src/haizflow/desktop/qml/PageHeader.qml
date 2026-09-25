import QtQuick
import QtQuick.Layouts
import "."

RowLayout {
    id: root
    objectName: "pageHeader"

    property string title: ""
    property string subtitle: ""
    default property alias actions: actionArea.data

    spacing: Theme.space24
    implicitHeight: Math.max(48, titleArea.implicitHeight, actionArea.implicitHeight)

    ColumnLayout {
        id: titleArea
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        spacing: Theme.space4

        Text {
            Layout.fillWidth: true
            text: root.title
            color: Theme.text
            font.family: Theme.fontFamily
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
            font.family: Theme.fontFamily
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
