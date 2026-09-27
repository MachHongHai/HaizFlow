import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    property string title: ""
    property string kind: ""
    property bool trackVisible: true
    property bool muted: false
    property bool selected: false
    property bool legacyReadOnly: false
    property bool secondaryAudioTrack: false
    property bool secondaryMuted: false
    readonly property bool audioTrack: ["voice", "source_audio", "music"].indexOf(kind) >= 0
    readonly property bool menuAvailable: !legacyReadOnly || audioTrack || secondaryAudioTrack

    signal visibilityToggled()
    signal muteToggled()
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
            visible: root.menuAvailable
            controlSize: 28
            iconName: !root.trackVisible ? "hide"
                : root.muted || root.secondaryMuted ? "muted" : "more"
            toolTipText: qsTr("Tùy chọn track")
            onClicked: trackMenu.popup()
        }
    }

    TopBarPopupMenu {
        id: trackMenu
        menuContentWidth: 188

        AppMenuItem {
            text: root.trackVisible ? qsTr("Ẩn layer") : qsTr("Hiện layer")
            collapsed: root.legacyReadOnly
            iconGlyph: root.trackVisible ? "\uED1A" : "\uE890"
            onTriggered: root.visibilityToggled()
        }
        AppMenuItem {
            collapsed: !root.audioTrack
            text: root.muted ? qsTr("Bật tiếng") : qsTr("Tắt tiếng")
            iconGlyph: root.muted ? "\uE767" : "\uE74F"
            onTriggered: root.muteToggled()
        }
        AppMenuItem {
            collapsed: !root.secondaryAudioTrack
            text: root.secondaryMuted ? qsTr("Bật giọng đọc") : qsTr("Tắt giọng đọc")
            iconGlyph: root.secondaryMuted ? "\uE767" : "\uE74F"
            onTriggered: root.secondaryMuteToggled()
        }
    }

    TapHandler {
        acceptedButtons: Qt.LeftButton
        onTapped: root.selectedRequested()
    }
}
