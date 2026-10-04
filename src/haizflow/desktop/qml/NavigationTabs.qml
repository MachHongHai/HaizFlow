pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

RowLayout {
    id: root
    property var options: []
    property string currentValue: ""
    signal activated(string value)
    spacing: Theme.space24
    Repeater {
        model: root.options
        delegate: Button {
            id: tab
            required property var modelData
            readonly property bool selected: root.currentValue === modelData.value
            text: modelData.label
            Layout.minimumWidth: implicitWidth
            implicitHeight: 44
            implicitWidth: label.implicitWidth + Theme.space16
            focusPolicy: Qt.TabFocus
            padding: Theme.space8
            Accessible.role: Accessible.PageTab
            Accessible.name: text
            Accessible.description: selected ? qsTr("Mục đang mở") : ""
            onClicked: root.activated(String(modelData.value))
            contentItem: Text {
                id: label
                text: tab.text
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.body
                font.weight: tab.selected ? Font.DemiBold : Font.Normal
                color: tab.selected || tab.hovered ? Theme.text : Theme.textMuted
                verticalAlignment: Text.AlignVCenter
            }
            background: Rectangle {
                color: tab.hovered ? Theme.surface : "transparent"
                radius: Theme.radiusSmall
                border.width: tab.visualFocus ? 1 : 0
                border.color: Theme.focus
                Rectangle {
                    anchors.bottom: parent.bottom
                    anchors.left: parent.left
                    anchors.right: parent.right
                    height: 2
                    visible: tab.selected
                    color: Theme.interactive
                    Accessible.ignored: true
                }
            }
        }
    }
}
