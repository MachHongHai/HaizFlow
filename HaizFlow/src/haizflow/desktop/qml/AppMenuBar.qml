pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    signal newSingleProjectRequested
    signal manualProjectRequested
    signal newBatchProjectRequested
    signal newDownloadProjectRequested
    signal newPublishProjectRequested
    signal settingsRequested
    signal aboutRequested
    signal helpRequested
    signal backRequested
    signal forwardRequested
    signal homeRequested

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

        TopBarNavigationButton {
            objectName: "homeNavigationButton"
            glyph: "\uE80F"
            toolTipText: qsTr("Trang chủ")
            onClicked: root.homeRequested()
        }

        Rectangle {
            Layout.preferredWidth: 1
            Layout.preferredHeight: 18
            Layout.leftMargin: Theme.space4
            Layout.rightMargin: Theme.space4
            color: Theme.divider
        }

        TopBarNavigationButton {
            objectName: "backNavigationButton"
            glyph: "\uE72B"
            toolTipText: qsTr("Quay lại")
            enabled: root.canGoBack
            onClicked: root.backRequested()
        }

        TopBarNavigationButton {
            objectName: "forwardNavigationButton"
            glyph: "\uE72A"
            toolTipText: qsTr("Tiến")
            enabled: root.canGoForward
            onClicked: root.forwardRequested()
        }

        Item {
            Layout.preferredWidth: Theme.space4
        }

        TopBarMenuButton {
            id: projectButton

            objectName: "projectMenuButton"
            text: qsTr("Dự án")
            onPressed: menuWasOpenOnPress = projectMenu.visible
            onClicked: root.toggleMenu(projectMenu, projectButton, menuWasOpenOnPress)
        }

        TopBarMenuButton {
            id: settingsButton

            objectName: "settingsMenuButton"
            text: qsTr("Cài đặt")
            onPressed: menuWasOpenOnPress = settingsMenu.visible
            onClicked: root.toggleMenu(settingsMenu, settingsButton, menuWasOpenOnPress)
        }

        Item {
            Layout.fillWidth: true
        }

        TopBarNavigationButton {
            id: helpButton

            objectName: "helpButton"
            glyph: "\uE897"
            toolTipText: qsTr("Trợ giúp")
            onClicked: {
                projectMenu.close();
                settingsMenu.close();
                root.helpRequested();
            }
        }
    }

    function toggleMenu(menu, anchorButton, wasOpenOnPress) {
        if (wasOpenOnPress || menu.visible) {
            menu.close();
            return;
        }

        projectMenu.close();
        settingsMenu.close();
        const anchorPosition = anchorButton.mapToItem(Overlay.overlay, 0, 0);
        const barBottom = root.mapToItem(Overlay.overlay, 0, root.height);
        menu.x = Math.round(anchorPosition.x);
        menu.y = Math.round(barBottom.y + Theme.space4);
        menu.open();
    }

    TopBarPopupMenu {
        id: projectMenu

        objectName: "projectMenuPopup"
        parent: Overlay.overlay
        menuContentWidth: Math.max(
            newSingleProjectItem.implicitWidth,
            newManualProjectItem.implicitWidth,
            newBatchProjectItem.implicitWidth,
            newDownloadProjectItem.implicitWidth,
            newPublishProjectItem.implicitWidth)

        AppMenuItem {
            id: newSingleProjectItem

            text: qsTr("Dự án Tự động mới")
            onTriggered: root.newSingleProjectRequested()
        }

        AppMenuItem {
            id: newManualProjectItem

            text: qsTr("Dự án Thủ công mới")
            onTriggered: root.manualProjectRequested()
        }

        AppMenuItem {
            id: newBatchProjectItem

            text: qsTr("Dự án Hàng loạt mới")
            onTriggered: root.newBatchProjectRequested()
        }

        MenuSeparator {}

        AppMenuItem {
            id: newDownloadProjectItem

            text: qsTr("Dự án Tải xuống mới")
            onTriggered: root.newDownloadProjectRequested()
        }

        AppMenuItem {
            id: newPublishProjectItem

            text: qsTr("Dự án Đăng mạng xã hội mới")
            onTriggered: root.newPublishProjectRequested()
        }
    }

    TopBarPopupMenu {
        id: settingsMenu

        objectName: "settingsMenuPopup"
        parent: Overlay.overlay
        menuContentWidth: Math.max(settingsItem.implicitWidth, aboutItem.implicitWidth)

        AppMenuItem {
            id: settingsItem

            text: qsTr("Cài đặt")
            onTriggered: root.settingsRequested()
        }

        AppMenuItem {
            id: aboutItem

            text: qsTr("Giới thiệu")
            onTriggered: root.aboutRequested()
        }
    }

}
