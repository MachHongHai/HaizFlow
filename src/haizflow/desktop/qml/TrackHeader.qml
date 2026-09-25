import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    property string title: ""
    property string kind: ""
    property bool trackVisible: true
    property bool locked: false
    property bool muted: false
    property bool solo: false
    property bool collapsed: false
    property bool selected: false
    property bool legacyReadOnly: false
    property bool secondaryAudioTrack: false
    property bool secondaryMuted: false
    readonly property bool audioTrack: ["voice", "source_audio", "music"].indexOf(kind) >= 0

    signal visibilityToggled()
    signal lockToggled()
    signal muteToggled()
    signal soloToggled()
    signal collapsedToggled()
    signal selectedRequested()
    signal secondaryMuteToggled()

    implicitWidth: 152
    implicitHeight: 40
    color: selected ? Theme.sidebarSelected : Theme.surface
    border.width: 1
    border.color: selected ? Theme.interactiveOutline : Theme.divider

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.space8
        anchors.rightMargin: Theme.space4
        spacing: 2

        Text {
            Layout.fillWidth: true
            text: root.title
            color: root.trackVisible && !root.muted ? Theme.text : Theme.textDisabled
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.metadata
            font.weight: root.selected ? Font.DemiBold : Font.Normal
            elide: Text.ElideRight
            textFormat: Text.PlainText
        }

        StudioIconButton {
            controlSize: 28
            iconName: !root.trackVisible ? "hide"
                : root.locked ? "lock"
                : root.muted ? "muted"
                : root.solo ? "solo"
                : root.secondaryMuted ? "muted" : "more"
            toolTipText: qsTr("Tùy chọn track")
            onClicked: trackMenu.popup()
        }
    }

    TopBarPopupMenu {
        id: trackMenu
        menuContentWidth: 176

        AppMenuItem {
            text: qsTr("Thu gọn track")
            checkable: true
            checked: root.collapsed
            onTriggered: root.collapsedToggled()
        }
        AppMenuItem {
            text: qsTr("Hiển thị")
            collapsed: root.legacyReadOnly
            checkable: true
            checked: root.trackVisible
            onTriggered: root.visibilityToggled()
        }
        AppMenuItem {
            text: qsTr("Khóa chỉnh sửa")
            collapsed: root.legacyReadOnly
            checkable: true
            checked: root.locked
            onTriggered: root.lockToggled()
        }
        AppMenuItem {
            collapsed: !root.audioTrack
            text: qsTr("Tắt tiếng")
            checkable: true
            checked: root.muted
            onTriggered: root.muteToggled()
        }
        AppMenuItem {
            collapsed: !root.audioTrack
            text: qsTr("Solo")
            checkable: true
            checked: root.solo
            onTriggered: root.soloToggled()
        }
        AppMenuItem {
            collapsed: !root.secondaryAudioTrack
            text: qsTr("Tắt tiếng giọng đọc")
            checkable: true
            checked: root.secondaryMuted
            onTriggered: root.secondaryMuteToggled()
        }
    }

    TapHandler {
        acceptedButtons: Qt.LeftButton
        onTapped: root.selectedRequested()
    }
}
