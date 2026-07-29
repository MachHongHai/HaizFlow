import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

RowLayout {
    id: root

    property string projectFolderText: I18n.t("Open project folder")
    property bool projectFolderEnabled: true
    property bool showInputVideo: false
    property bool inputVideoEnabled: true
    property bool showOutputFolder: false
    property bool outputFolderEnabled: true
    property bool setupVisible: false
    property bool setupEnabled: true
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
        toolTipText: I18n.t("More actions")
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
                text: I18n.t("Open input video")
                iconGlyph: "\uE714"
                collapsed: !root.showInputVideo
                enabled: root.inputVideoEnabled
                onTriggered: root.inputVideoRequested()
            }

            AppMenuItem {
                text: I18n.t("Open export folder")
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
                text: I18n.t("Batch setup")
                iconGlyph: "\uE713"
                collapsed: !root.setupVisible
                enabled: root.setupEnabled
                onTriggered: root.setupRequested()
            }

            AppMenuItem {
                text: I18n.t("Delete project")
                iconGlyph: "\uE74D"
                tone: "danger"
                enabled: root.deleteEnabled
                onTriggered: root.deleteRequested()
            }
        }
    }
}
