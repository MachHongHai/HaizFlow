import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

RowLayout {
    id: root

    property string projectFolderText: qsTr("Mở thư mục dự án")
    property bool projectFolderEnabled: true
    property bool showInputVideo: false
    property bool inputVideoEnabled: true
    property bool showOutputFolder: false
    property bool outputFolderEnabled: true
    property bool setupVisible: false
    property bool setupEnabled: true
    property string deleteText: qsTr("Xóa dự án")
    property bool deleteEnabled: true

    signal projectFolderRequested()
    signal inputVideoRequested()
    signal outputFolderRequested()
    signal setupRequested()
    signal deleteRequested()

    spacing: Theme.space8

    IconButton {
        id: moreButton

        property bool menuWasOpenOnPress: false

        controlSize: 34
        glyph: "\uE712"
        // The ellipsis already communicates a menu.  Suppress the hover tooltip
        // so it cannot remain above the popup after the menu is opened.
        Accessible.name: qsTr("Thao tác khác")
        onPressed: menuWasOpenOnPress = actionMenu.visible
        onClicked: {
            if (menuWasOpenOnPress || actionMenu.visible)
                actionMenu.close()
            else
                actionMenu.open()
        }

        Menu {
            id: actionMenu

            width: 224
            y: parent.height + Theme.space4
            padding: Theme.space4
            closePolicy: Popup.CloseOnEscape | Popup.CloseOnReleaseOutside

            background: Rectangle {
                radius: Theme.radiusSmall
                color: Theme.surfaceElevated
                border.width: 1
                border.color: Theme.outlineStrong
            }

            AppMenuItem {
                text: qsTr("Mở video nguồn")
                iconGlyph: "\uE714"
                collapsed: !root.showInputVideo
                enabled: root.inputVideoEnabled
                onTriggered: root.inputVideoRequested()
            }

            AppMenuItem {
                text: qsTr("Mở thư mục video xuất")
                iconGlyph: "\uE8B7"
                collapsed: !root.showOutputFolder
                enabled: root.outputFolderEnabled
                onTriggered: root.outputFolderRequested()
            }

            AppMenuItem {
                text: root.projectFolderText
                iconGlyph: "\uE8B7"
                enabled: root.projectFolderEnabled
                onTriggered: root.projectFolderRequested()
            }

            AppMenuItem {
                text: qsTr("Cài đặt hàng loạt")
                iconGlyph: "\uE713"
                collapsed: !root.setupVisible
                enabled: root.setupEnabled
                onTriggered: root.setupRequested()
            }

            AppMenuItem {
                text: root.deleteText
                iconGlyph: "\uE74D"
                tone: "danger"
                enabled: root.deleteEnabled
                onTriggered: root.deleteRequested()
            }
        }
    }
}
