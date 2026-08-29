import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root

    property string title: ""
    property string helpText: ""
    default property alias content: sectionContent.data
    spacing: Theme.space8

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space4

        Text {
            Layout.fillWidth: true
            text: root.title
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.section
            font.weight: Font.DemiBold
            textFormat: Text.PlainText
        }

        HelpPopover {
            visible: root.helpText.length > 0
            helpText: root.helpText
            accessibleLabel: root.title
        }
    }

    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: 1
        color: Theme.divider
    }

    ColumnLayout {
        id: sectionContent
        Layout.fillWidth: true
        spacing: Theme.space8
    }
}
