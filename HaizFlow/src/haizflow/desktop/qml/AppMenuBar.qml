pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    signal newSingleProjectRequested
    signal newBatchProjectRequested
    signal newDownloadProjectRequested
    signal newPublishProjectRequested
    signal settingsRequested
    signal aboutRequested
    signal backRequested
    signal forwardRequested

    property bool canGoBack: false
    property bool canGoForward: false

    implicitHeight: 40
    color: Theme.topBar

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 1
        color: Theme.divider
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.space12
        anchors.rightMargin: Theme.space12
        spacing: 2

        NavigationButton {
            glyph: "\uE72B"
            toolTipText: I18n.t("Back")
            enabled: root.canGoBack
            onClicked: root.backRequested()
        }

        NavigationButton {
            glyph: "\uE72A"
            toolTipText: I18n.t("Forward")
            enabled: root.canGoForward
            onClicked: root.forwardRequested()
        }

        Item {
            Layout.preferredWidth: Theme.space4
        }

        AppMenuButton {
            id: projectButton

            objectName: "projectMenuButton"
            text: I18n.t("Project")
            onPressed: menuWasOpenOnPress = projectMenu.visible
            onClicked: root.toggleMenu(projectMenu, projectButton, menuWasOpenOnPress)
        }

        AppMenuButton {
            id: settingsButton

            objectName: "settingsMenuButton"
            text: I18n.t("Settings")
            onPressed: menuWasOpenOnPress = settingsMenu.visible
            onClicked: root.toggleMenu(settingsMenu, settingsButton, menuWasOpenOnPress)
        }

        Item {
            Layout.fillWidth: true
        }
    }

    function toggleMenu(menu, anchorButton, wasOpenOnPress) {
        if (wasOpenOnPress || menu.visible) {
            menu.close()
            return
        }

        projectMenu.close()
        settingsMenu.close()
        const anchorPosition = anchorButton.mapToItem(Overlay.overlay, 0, 0)
        const barBottom = root.mapToItem(Overlay.overlay, 0, root.height)
        menu.x = Math.round(anchorPosition.x)
        menu.y = Math.round(barBottom.y + Theme.space4)
        menu.open()
    }

    AppPopupMenu {
        id: projectMenu

        objectName: "projectMenuPopup"
        parent: Overlay.overlay
        menuContentWidth: Math.max(
            newSingleProjectItem.implicitWidth,
            newBatchProjectItem.implicitWidth,
            newDownloadProjectItem.implicitWidth,
            newPublishProjectItem.implicitWidth
        )

        AppMenuItem {
            id: newSingleProjectItem

            text: I18n.t("New single project")
            onTriggered: root.newSingleProjectRequested()
        }

        AppMenuItem {
            id: newBatchProjectItem

            text: I18n.t("New batch project")
            onTriggered: root.newBatchProjectRequested()
        }

        AppMenuItem {
            id: newDownloadProjectItem

            text: I18n.t("New download project")
            onTriggered: root.newDownloadProjectRequested()
        }

        AppMenuItem {
            id: newPublishProjectItem

            text: I18n.t("New social publishing project")
            onTriggered: root.newPublishProjectRequested()
        }

    }

    AppPopupMenu {
        id: settingsMenu

        objectName: "settingsMenuPopup"
        parent: Overlay.overlay
        menuContentWidth: Math.max(settingsItem.implicitWidth, aboutItem.implicitWidth)

        AppMenuItem {
            id: settingsItem

            text: I18n.t("Settings")
            onTriggered: root.settingsRequested()
        }

        AppMenuItem {
            id: aboutItem

            text: I18n.t("About & contact")
            onTriggered: root.aboutRequested()
        }
    }

    component AppMenuButton: Button {
        id: button

        property bool menuWasOpenOnPress: false

        implicitHeight: 28
        leftPadding: 10
        rightPadding: 10
        topPadding: 0
        bottomPadding: 0
        focusPolicy: Qt.TabFocus
        Accessible.name: text

        contentItem: Text {
            text: button.text
            color: button.enabled
                ? (button.hovered || button.down ? Theme.text : Theme.textMuted)
                : Theme.textDisabled
            font.pixelSize: Theme.caption
            font.weight: Font.Normal
            verticalAlignment: Text.AlignVCenter
            textFormat: Text.PlainText
        }

        background: Rectangle {
            radius: Theme.radiusSmall
            color: button.down ? Theme.windowCaptionPressed
                : button.hovered || button.activeFocus ? Theme.windowCaptionHover : "transparent"
            border.width: 0
        }
    }

    component NavigationButton: Button {
        id: button

        property string glyph: ""
        property string toolTipText: ""

        implicitWidth: 28
        implicitHeight: 28
        leftPadding: 0
        rightPadding: 0
        topPadding: 0
        bottomPadding: 0
        focusPolicy: Qt.TabFocus
        Accessible.name: toolTipText
        ToolTip.visible: hovered && toolTipText.length > 0
        ToolTip.text: toolTipText
        ToolTip.delay: 450

        contentItem: AppIcon {
            glyph: button.glyph
            iconSize: 14
            iconColor: button.enabled
                ? (button.hovered || button.down ? Theme.text : Theme.textMuted)
                : Theme.textDisabled
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }

        background: Rectangle {
            radius: Theme.radiusSmall
            color: button.down ? Theme.windowCaptionPressed
                : button.hovered || button.activeFocus ? Theme.windowCaptionHover : "transparent"
            border.width: 0
        }
    }

    component AppPopupMenu: Menu {
        property real menuContentWidth: 0

        width: Math.min(menuContentWidth + padding * 2, 210)
        modal: false
        padding: Theme.space4
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnReleaseOutside

        background: Rectangle {
            radius: Theme.radiusSmall
            color: Theme.surface
            border.width: 0
        }
    }
}
