pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    property bool compact: false
    property string currentSection: "home"
    signal sectionRequested(string section)

    implicitWidth: compact ? UiMetrics.navigationCompact : UiMetrics.navigationExpanded
    color: Theme.sidebar

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.space12
        spacing: Theme.space8

        Text {
            Layout.fillWidth: true
            Layout.preferredHeight: 48
            visible: !root.compact
            text: "HaizFlow"
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.body
            font.weight: Font.DemiBold
            verticalAlignment: Text.AlignVCenter
            textFormat: Text.PlainText
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            Layout.bottomMargin: Theme.space8
            color: Theme.divider
        }

        Repeater {
            model: [
                { key: "home", label: qsTr("Trang chủ"), icon: "home" },
                { key: "projects", label: qsTr("Dự án"), icon: "projects" },
                { key: "downloads", label: qsTr("Tải xuống"), icon: "download" },
                { key: "social", label: qsTr("Đăng mạng xã hội"), icon: "share" }
            ]

            delegate: Rectangle {
                id: navItem
                required property var modelData
                Layout.fillWidth: true
                Layout.preferredHeight: 36
                radius: Theme.radiusTiny
                color: root.currentSection === modelData.key ? Theme.sidebarSelected
                    : navHover.hovered ? Theme.sidebarHover : "transparent"
                border.width: activeFocus ? 2 : 0
                border.color: Theme.focus
                activeFocusOnTab: true
                Accessible.role: Accessible.Button
                Accessible.name: modelData.label

                Rectangle {
                    anchors.left: parent.left
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    anchors.topMargin: 7
                    anchors.bottomMargin: 7
                    width: 2
                    radius: 1
                    visible: root.currentSection === navItem.modelData.key
                    color: Theme.interactive
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: root.compact ? 0 : Theme.space12
                    anchors.rightMargin: root.compact ? 0 : Theme.space12
                    spacing: Theme.space12

                    FluentIcon {
                        Layout.preferredWidth: root.compact ? parent.width : 18
                        Layout.preferredHeight: 18
                        name: navItem.modelData.icon
                        iconColor: root.currentSection === navItem.modelData.key ? Theme.text : Theme.textMuted
                        iconSize: 17
                    }
                    Text {
                        Layout.fillWidth: true
                        visible: !root.compact
                        text: navItem.modelData.label
                        color: root.currentSection === navItem.modelData.key ? Theme.text : Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: TypeScale.control
                        font.weight: root.currentSection === navItem.modelData.key ? Font.DemiBold : Font.Normal
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                    }
                }

                HoverHandler { id: navHover; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: root.sectionRequested(navItem.modelData.key) }
                Keys.onReturnPressed: root.sectionRequested(navItem.modelData.key)
                Keys.onSpacePressed: root.sectionRequested(navItem.modelData.key)
            }
        }

        Item { Layout.fillHeight: true }

    }

    Rectangle {
        anchors.right: parent.right
        height: parent.height
        width: 1
        color: Theme.divider
    }
}
