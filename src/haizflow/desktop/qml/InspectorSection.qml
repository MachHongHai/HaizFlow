import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root

    property string title: ""
    property string summary: ""
    property bool collapsible: true
    property bool expanded: true
    default property alias contentItem: contentColumn.data

    Layout.fillWidth: true
    spacing: Theme.space8

    Rectangle {
        Layout.fillWidth: true
        implicitHeight: 40
        color: headerArea.containsMouse && root.collapsible ? Theme.surfaceMuted : "transparent"
        radius: Theme.radiusSmall
        activeFocusOnTab: root.collapsible
        Accessible.role: Accessible.Button
        Accessible.name: root.title
        Accessible.description: root.expanded ? qsTr("Đang mở") : qsTr("Đã thu gọn")
        Keys.onReturnPressed: root.expanded = !root.expanded
        Keys.onSpacePressed: root.expanded = !root.expanded
        border.width: activeFocus ? 2 : 0
        border.color: Theme.focus

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: Theme.space8
            anchors.rightMargin: Theme.space8
            spacing: Theme.space8

            Text {
                Layout.fillWidth: true
                text: root.title
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.control
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
            }

            Text {
                visible: root.summary.length > 0
                text: root.summary
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.metadata
                textFormat: Text.PlainText
            }

            FluentIcon {
                visible: root.collapsible
                Layout.preferredWidth: 20
                Layout.preferredHeight: 20
                name: root.expanded ? "chevronUp" : "chevronDown"
                iconColor: Theme.textMuted
            }
        }

        MouseArea {
            id: headerArea
            anchors.fill: parent
            enabled: root.collapsible
            hoverEnabled: true
            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: root.expanded = !root.expanded
        }
    }

    ColumnLayout {
        id: contentColumn
        visible: root.expanded
        Layout.fillWidth: true
        Layout.leftMargin: Theme.space8
        Layout.rightMargin: Theme.space8
        spacing: Theme.space8
    }

    Rectangle {
        visible: root.expanded
        Layout.fillWidth: true
        Layout.topMargin: Theme.space4
        implicitHeight: 1
        color: Theme.divider
    }
}
