import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    required property int modelIndex
    required property string projectName
    required property string projectType
    required property string status
    required property int progress
    required property string thumbnailSource
    required property string updatedAt
    property string typeLabel: projectType
    property string statusLabel: status
    signal activated(int index, string projectType)

    function updatedLabel(value) {
        const updated = new Date(value)
        if (isNaN(updated.getTime()))
            return ""
        const locale = Qt.locale(AppController.settingsLanguage === "vi" ? "vi_VN" : "en_US")
        const pattern = updated.getFullYear() === new Date().getFullYear()
            ? "dd/MM HH:mm" : "dd/MM/yy"
        return locale.toString(updated, pattern)
    }

    implicitHeight: 64
    color: hoverHandler.hovered ? Theme.surfaceMuted : "transparent"
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: projectName

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.space12
        anchors.rightMargin: Theme.space12
        spacing: Theme.space12

        MediaThumbnail {
            Layout.preferredWidth: 72
            Layout.preferredHeight: 44
            source: root.thumbnailSource
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Text {
                Layout.fillWidth: true
                text: root.projectName
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.control
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
                elide: Text.ElideRight
            }
            Text {
                text: root.typeLabel
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: TypeScale.metadata
                textFormat: Text.PlainText
            }
        }

        Text {
            Layout.preferredWidth: 112
            text: root.status === "processing"
                ? root.statusLabel + " " + qsTr("%1%").arg(root.progress)
                : root.statusLabel
            color: root.status === "failed" ? Theme.danger : Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.metadata
            textFormat: Text.PlainText
            elide: Text.ElideRight
        }

        Text {
            Layout.preferredWidth: 108
            visible: root.width >= 690
            text: root.updatedLabel(root.updatedAt)
            color: Theme.textSubtle
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.metadata
            textFormat: Text.PlainText
            elide: Text.ElideRight
        }

    }

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 1
        color: Theme.divider
    }

    HoverHandler { id: hoverHandler; cursorShape: Qt.PointingHandCursor }
    TapHandler { onTapped: root.activated(root.modelIndex, root.projectType) }
    Keys.onReturnPressed: root.activated(root.modelIndex, root.projectType)
    Keys.onSpacePressed: root.activated(root.modelIndex, root.projectType)
}
