pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root
    property QtObject controller: AppController
    property string segmentId: ""
    property string savedText: ""
    property int revision: 0
    property string saveStatus: "saved"
    property string editingId: ""
    property int editingRevision: 0
    property string committedText: ""
    property bool installing: false
    property int serial: 0
    property string requestId: ""
    signal commitRequested(string segmentId, string text, int revision, string requestId)
    spacing: 8

    function commit() {
        saveTimer.stop();
        if (!editingId || editor.text === committedText)
            return;
        requestId = editingId + ":" + (++serial);
        committedText = editor.text;
        saveStatus = "saving";
        commitRequested(editingId, editor.text, editingRevision, requestId);
    }
    function dismiss() {
        commit();
        editor.deselect();
        editor.focus = false;
    }
    function focusEditor() { editor.forceActiveFocus(); }
    function install() {
        if (editingId === segmentId)
            return;
        commit();
        installing = true;
        editingId = segmentId;
        editingRevision = revision;
        editor.text = savedText;
        committedText = savedText;
        saveStatus = "saved";
        installing = false;
    }
    onSegmentIdChanged: Qt.callLater(install)
    onRevisionChanged: if (editingId === segmentId) editingRevision = revision
    onSavedTextChanged: {
        if (!editor.activeFocus && saveStatus === "saved" && editingId === segmentId) {
            installing = true;
            editor.text = savedText;
            committedText = savedText;
            installing = false;
        }
    }
    Component.onCompleted: install()
    Component.onDestruction: commit()

    ScrollView {
        contentWidth: availableWidth
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.minimumHeight: 220
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        TextArea {
            id: editor
            objectName: "manualSubtitleTextInput"
            enabled: root.segmentId.length > 0
            wrapMode: TextEdit.Wrap
            textFormat: TextEdit.PlainText
            selectByMouse: true
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: 14
            padding: 12
            Accessible.name: qsTr("Nội dung phụ đề")
            background: Rectangle {
                color: Theme.input
                radius: 4
                border.width: 1
                border.color: editor.activeFocus ? Theme.focus : Theme.outline
            }
            onTextChanged: {
                if (!root.installing) {
                    root.saveStatus = "dirty";
                    saveTimer.restart();
                }
            }
            Keys.onEscapePressed: root.dismiss()
            onActiveFocusChanged: if (!activeFocus) root.commit()
        }
    }
    RowLayout {
        Layout.fillWidth: true
        Text {
            Layout.fillWidth: true
            color: root.saveStatus === "error" ? Theme.danger : Theme.textMuted
            font.pixelSize: 12
            text: root.saveStatus === "saving" || root.saveStatus === "dirty" ? qsTr("Đang lưu…")
                : root.saveStatus === "error" ? qsTr("Không lưu được") : qsTr("Đã lưu")
        }
        StudioButton {
            visible: root.saveStatus === "error"
            text: qsTr("Thử lại")
            onClicked: { root.committedText = "\u0000"; root.commit(); }
        }
        Text { text: qsTr("%1 ký tự").arg(editor.length); color: Theme.textMuted; font.pixelSize: 12 }
    }
    Timer { id: saveTimer; interval: 500; onTriggered: root.commit() }
    Connections {
        target: root.controller
        function onManualSubtitleSaved(id, version, request) {
            if (id === root.editingId && request === root.requestId)
                root.saveStatus = editor.text === root.committedText ? "saved" : "dirty";
        }
        function onManualSubtitleSaveFailed(id, request, message) {
            if (id === root.editingId && request === root.requestId)
                root.saveStatus = "error";
        }
    }
}
