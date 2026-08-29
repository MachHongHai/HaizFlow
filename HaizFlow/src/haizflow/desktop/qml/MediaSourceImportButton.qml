import QtQuick
import QtQuick.Controls.Basic
import "."

AppButton {
    id: root

    signal fileRequested()
    signal linkRequested()
    signal downloadProjectRequested()

    property bool menuWasOpenOnPress: false

    text: qsTr("Nhập nguồn")
    iconGlyph: "\uE710"
    compact: true
    tone: "secondary"
    toolTipText: qsTr("Chọn tệp, liên kết hoặc video từ dự án tải xuống")

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
            text: qsTr("Tệp")
            iconGlyph: "\uE8B7"
            onTriggered: root.fileRequested()
        }

        AppMenuItem {
            text: qsTr("Liên kết")
            iconGlyph: "\uE71B"
            onTriggered: root.linkRequested()
        }

        AppMenuItem {
            text: qsTr("Tải xuống")
            iconGlyph: "\uE896"
            onTriggered: root.downloadProjectRequested()
        }
    }
}
