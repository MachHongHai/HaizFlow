pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    property var inspector
    id: subtitlePane
    spacing: Theme.space8
    height: implicitHeight
    readonly property string selectedSegmentId: subtitlePane.inspector.selectedSubtitle
        ? String(subtitlePane.inspector.selectedSubtitle.segment_id || "") : ""
    readonly property var selectedDraft: subtitlePane.inspector.subtitleDrafts[selectedSegmentId] || null

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space8
        Text {
            Layout.fillWidth: true
            text: subtitlePane.inspector.selectedSubtitle
                ? qsTr("%1 / %2").arg(subtitlePane.inspector.selectedSubtitleIndex + 1).arg(subtitlePane.inspector.subtitleSegments.length)
                : qsTr("Chưa chọn phụ đề")
            color: subtitlePane.inspector.selectedSubtitle ? Theme.text : Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.control
            font.weight: subtitlePane.inspector.selectedSubtitle ? Font.DemiBold : Font.Normal
            textFormat: Text.PlainText
            elide: Text.ElideRight
        }
        StudioIconButton {
            iconName: "back"
            toolTipText: qsTr("Phụ đề trước")
            enabled: subtitlePane.inspector.selectedSubtitleIndex > 0
            onClicked: subtitlePane.inspector.subtitleSelected(subtitlePane.inspector.selectedSubtitleIndex - 1)
        }
        StudioIconButton {
            iconName: "forward"
            toolTipText: qsTr("Phụ đề sau")
            enabled: subtitlePane.inspector.selectedSubtitleIndex >= 0
                && subtitlePane.inspector.selectedSubtitleIndex < subtitlePane.inspector.subtitleSegments.length - 1
            onClicked: subtitlePane.inspector.subtitleSelected(subtitlePane.inspector.selectedSubtitleIndex + 1)
        }
    }
    Text {
        Layout.fillWidth: true
        text: subtitlePane.selectedDraft !== null
            ? String(subtitlePane.selectedDraft.text || "")
            : subtitlePane.inspector.selectedSubtitle
                ? String(subtitlePane.inspector.selectedSubtitle.text || "")
                : qsTr("Chọn phụ đề trên video hoặc timeline.")
        color: subtitlePane.inspector.selectedSubtitle ? Theme.text : Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: TypeScale.control
        wrapMode: Text.Wrap
        textFormat: Text.PlainText
        elide: Text.ElideRight
        maximumLineCount: 2
    }
    Repeater {
        model: subtitlePane.inspector.selectedEditorClip.warnings || []
        delegate: InlineBanner {
            required property var modelData
            Layout.fillWidth: true
            tone: "warning"
            message: String(modelData.message || "")
        }
    }
    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space8

        Item { Layout.fillWidth: true }

        StudioButton {
            text: qsTr("Mở rộng")
            iconName: "fullscreen"
            variant: "secondary"
            enabled: subtitlePane.inspector.selectedSubtitle !== null
            onClicked: subtitlePane.inspector.focusTextEditor()
        }
    }

    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: 1
        color: Theme.divider
    }
    ManualSubtitleStyleControls {
        Layout.fillWidth: true
        editable: subtitlePane.inspector.editable
        onStyleCommitted: subtitlePane.inspector.settingsCommitted()
    }
}
