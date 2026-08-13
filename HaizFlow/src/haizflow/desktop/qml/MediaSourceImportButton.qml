import QtQuick
import QtQuick.Controls.Basic
import "."

AppButton {
    id: root

    signal fileRequested()
    signal linkRequested()
    signal downloadProjectRequested()

    property bool menuWasOpenOnPress: false

    text: I18n.t("Import source")
    iconGlyph: "\uE710"
    compact: true
    tone: "secondary"
    toolTipText: I18n.t("Choose a file, link, or downloaded video")

    function openMenu() {
        if (!enabled)
            return
        sourceMenu.open()
    }

    onPressed: menuWasOpenOnPress = sourceMenu.visible
    onClicked: {
        if (menuWasOpenOnPress || sourceMenu.visible)
            sourceMenu.close()
        else
            sourceMenu.open()
    }

    Menu {
        id: sourceMenu

        width: 224
        y: root.height + Theme.space4
        padding: 6
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnReleaseOutside

        background: Rectangle {
            color: Theme.surfaceElevated
            radius: Theme.radius
            border.width: 1
            border.color: Theme.outlineStrong
        }

        AppMenuItem {
            text: I18n.t("File")
            iconGlyph: "\uE8B7"
            onTriggered: root.fileRequested()
        }

        AppMenuItem {
            text: I18n.t("Link")
            iconGlyph: "\uE71B"
            onTriggered: root.linkRequested()
        }

        AppMenuItem {
            text: I18n.t("Downloads")
            iconGlyph: "\uE896"
            onTriggered: root.downloadProjectRequested()
        }
    }
}
