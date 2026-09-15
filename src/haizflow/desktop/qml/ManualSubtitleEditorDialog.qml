pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

AppDialog {
    id: root
    objectName: "manualSubtitleEditorDialog"

    property QtObject controller: AppController
    property var segment: null
    property int selectedIndex: -1
    property int segmentCount: 0
    property bool hasInitialDraft: false
    property string initialDraftText: ""

    signal previousRequested()
    signal nextRequested()
    signal commitRequested(string segmentId, string text, int revision, string requestId)
    signal draftChanged(string segmentId, string text, int revision)
    signal draftCleared(string segmentId)
    signal editingClosed()

    readonly property string segmentId: segment ? String(segment.segment_id || "") : ""
    readonly property string segmentText: segment ? String(segment.text || "") : ""
    readonly property int segmentRevision: segment ? Number(segment.revision || 0) : 0

    title: qsTr("Sửa phụ đề")
    subtitle: segment
        ? qsTr("Đoạn %1/%2 · %3 — %4")
            .arg(selectedIndex + 1)
            .arg(segmentCount)
            .arg(formatTime(Number(segment.start || 0)))
            .arg(formatTime(Number(segment.end || 0)))
        : qsTr("Chưa chọn phụ đề")
    preferredWidth: 1080
    maximumWidth: 1240
    preferredHeight: 760
    maximumHeight: 900

    function formatTime(secondsValue) {
        const totalMs = Math.max(0, Math.round((Number(secondsValue) || 0) * 1000));
        const minutes = Math.floor(totalMs / 60000);
        const seconds = Math.floor((totalMs % 60000) / 1000);
        const millis = totalMs % 1000;
        return String(minutes).padStart(2, "0") + ":"
            + String(seconds).padStart(2, "0") + "."
            + String(millis).padStart(3, "0");
    }

    function openForSelection() {
        open();
        Qt.callLater(subtitleEditor.focusEditor);
    }

    function closeEditor() {
        subtitleEditor.dismiss();
        close();
    }

    onClosed: root.editingClosed()

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space12

        Text {
            Layout.fillWidth: true
            text: root.segment
                ? qsTr("Đoạn %1 / %2").arg(root.selectedIndex + 1).arg(root.segmentCount)
                : qsTr("Chưa chọn phụ đề")
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.body
            font.weight: Font.DemiBold
            textFormat: Text.PlainText
        }

        StudioIconButton {
            iconName: "back"
            toolTipText: qsTr("Phụ đề trước")
            enabled: root.selectedIndex > 0
            onClicked: root.previousRequested()
        }

        StudioIconButton {
            iconName: "forward"
            toolTipText: qsTr("Phụ đề sau")
            enabled: root.selectedIndex >= 0 && root.selectedIndex < root.segmentCount - 1
            onClicked: root.nextRequested()
        }
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.space12

        Text {
            Layout.fillWidth: true
            text: qsTr("Nội dung")
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.label
            font.weight: Font.DemiBold
            textFormat: Text.PlainText
        }

        Text {
            text: qsTr("Ctrl+Enter để lưu")
            color: Theme.textSubtle
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.metadata
            textFormat: Text.PlainText
        }
    }

    SubtitleTextEditor {
        id: subtitleEditor
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.minimumHeight: 440
        controller: root.controller
        segmentId: root.segmentId
        savedText: root.segmentText
        revision: root.segmentRevision
        hasInitialDraft: root.hasInitialDraft
        initialDraftText: root.initialDraftText
        minimumEditorHeight: 440
        editorFontSize: 15
        onCommitRequested: function(id, text, version, request) {
            root.commitRequested(id, text, version, request);
        }
        onDraftChanged: function(id, text, version) {
            root.draftChanged(id, text, version);
        }
        onDraftCleared: function(id) { root.draftCleared(id); }
    }
}
