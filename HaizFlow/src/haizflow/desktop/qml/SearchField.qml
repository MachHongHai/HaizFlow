import QtQuick
import "."

AppTextField {
    id: root

    leftPadding: 38
    placeholderText: qsTr("Tìm kiếm")

    FluentIcon {
        anchors.left: parent.left
        anchors.leftMargin: 12
        anchors.verticalCenter: parent.verticalCenter
        width: Theme.icon
        height: Theme.icon
        name: "search"
        iconColor: root.activeFocus ? Theme.interactive : Theme.textSubtle
        iconSize: Theme.iconSmall
    }
}
