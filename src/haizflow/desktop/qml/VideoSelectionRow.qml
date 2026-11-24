pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root
    property string label: ""
    property string description: ""
    property string metadata: ""
    property string badgeLabel: ""
    property string badgeState: "ready"
    property url thumbnailSource: ""
    property bool selected: false
    signal selectionRequested(bool selected)
    signal selectionFocused()

    implicitHeight: 66
    radius: Theme.radiusSmall
    color: selected ? Theme.sidebarSelected : Theme.surfaceMuted
    border.width: 1
    border.color: selected ? Theme.outlineStrong : Theme.outline

    TapHandler {
        onTapped: point => {
            if (!check.contains(check.mapFromItem(root, point.position))) {
                check.forceActiveFocus(Qt.MouseFocusReason);
                root.selectionRequested(!root.selected);
            }
        }
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: Theme.space8
        spacing: Theme.space12

        MediaThumbnail {
            objectName: "videoSelectionThumbnail"
            Layout.preferredWidth: root.width < 480 ? 64 : 84
            Layout.fillHeight: true
            source: root.thumbnailSource
            Accessible.ignored: true
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 1
            Text {
                Layout.fillWidth: true
                text: root.label
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.control
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
                elide: Text.ElideMiddle
            }
            Text {
                Layout.fillWidth: true
                visible: text.length > 0
                text: root.description
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.metadata
                textFormat: Text.PlainText
                elide: Text.ElideMiddle
            }
        }
        StatusBadge { visible: root.badgeLabel.length > 0; label: root.badgeLabel; status: root.badgeState }
        Text {
            visible: root.width >= 460 && text.length > 0
            text: root.metadata
            color: Theme.textMuted
            font.pixelSize: TypeScale.metadata
            textFormat: Text.PlainText
        }
        StudioCheckBox {
            id: check
            objectName: "videoSelectionCheckBox"
            checked: root.selected
            Accessible.name: qsTr("Chọn %1").arg(root.label)
            Accessible.description: [root.description, root.badgeLabel, root.metadata].filter(value => value.length > 0).join(" · ")
            onToggled: root.selectionRequested(checked)
            onActiveFocusChanged: if (activeFocus) root.selectionFocused()
        }
    }
}
