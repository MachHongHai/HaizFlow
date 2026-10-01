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
    property bool showVideoFolder: false
    property bool videoFolderEnabled: true
    property bool showTechnicalLog: false
    property bool technicalLogEnabled: true
    property bool setupVisible: false
    property bool setupEnabled: true
    property string deleteText: qsTr("Xóa dự án")
    property bool deleteEnabled: true
    property string menuProjectKey: ""

    signal projectFolderRequested()
    signal inputVideoRequested()
    signal videoFolderRequested()
    signal technicalLogRequested()
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
            onAboutToShow: root.menuProjectKey = AppController.projectKey

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
                text: qsTr("Mở thư mục video")
                iconGlyph: "\uE8B7"
                collapsed: !root.showVideoFolder
                enabled: root.videoFolderEnabled
                onTriggered: root.videoFolderRequested()
            }

            AppMenuItem {
                text: root.projectFolderText
                iconGlyph: "\uE8B7"
                enabled: root.projectFolderEnabled
                onTriggered: root.projectFolderRequested()
            }

            AppMenuItem {
                text: qsTr("Log kỹ thuật")
                iconGlyph: "\uE9D9"
                collapsed: !root.showTechnicalLog
                enabled: root.technicalLogEnabled
                onTriggered: root.technicalLogRequested()
            }

            AppMenuItem {
                text: qsTr("Cài đặt hàng loạt")
                iconGlyph: "\uE713"
                collapsed: !root.setupVisible
                enabled: root.setupEnabled
                onTriggered: root.setupRequested()
            }

            AppMenuItem {
                text: qsTr("Đổi tên")
                iconGlyph: IconCatalog.glyph("edit")
                enabled: root.menuProjectKey.length > 0
                onTriggered: AppController.requestProjectRename(root.menuProjectKey)
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
