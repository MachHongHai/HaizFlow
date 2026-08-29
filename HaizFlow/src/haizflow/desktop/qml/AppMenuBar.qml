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
            glyph: "\uE72B"
            toolTipText: qsTr("Quay lại")
            enabled: root.canGoBack
            onClicked: root.backRequested()
        }

        TopBarNavigationButton {
            glyph: "\uE72A"
            toolTipText: qsTr("Tiến")
            enabled: root.canGoForward
            onClicked: root.forwardRequested()
        }

        TopBarNavigationButton {
            glyph: "\uE80F"
            toolTipText: qsTr("Trang chủ")
            onClicked: root.homeRequested()
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

        Item {
            Layout.fillWidth: true
        }

        TopBarNavigationButton {
            id: settingsButton

            objectName: "settingsButton"
            glyph: "\uE713"
            toolTipText: qsTr("Cài đặt")
            onClicked: {
                projectMenu.close();
                helpMenu.close();
                root.settingsRequested();
            }
        }

        TopBarNavigationButton {
            id: helpButton

            objectName: "helpMenuButton"
            glyph: "\uE897"
            toolTipText: qsTr("Trợ giúp")
            onPressed: menuWasOpenOnPress = helpMenu.visible
            onClicked: root.toggleMenu(helpMenu, helpButton, menuWasOpenOnPress)
        }
    }

    function toggleMenu(menu, anchorButton, wasOpenOnPress) {
        if (wasOpenOnPress || menu.visible) {
            menu.close();
            return;
        }

        projectMenu.close();
        helpMenu.close();
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
        id: helpMenu

        objectName: "helpMenuPopup"
        parent: Overlay.overlay
        menuContentWidth: aboutItem.implicitWidth

        AppMenuItem {
            id: aboutItem

            text: qsTr("Giới thiệu")
            onTriggered: root.aboutRequested()
        }
    }

}
