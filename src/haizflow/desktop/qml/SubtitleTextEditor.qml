pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root
    property QtObject controller: AppController
    property bool sessionActive: true
    property string segmentId: ""
    property string savedText: ""
    property int revision: 0
    property bool hasInitialDraft: false
    property string initialDraftText: ""
    property string saveStatus: "saved"
    property string editingId: ""
    property int editingRevision: 0
    property string committedText: ""
    property string pendingText: ""
    property bool installing: false
    property int serial: 0
    readonly property string instanceToken: Date.now().toString(36) + "-" + Math.random().toString(36).slice(2)
    property string requestId: ""
    property string errorMessage: ""
    property int minimumEditorHeight: 220
    property int editorFontSize: TypeScale.body
    readonly property bool hasChanges: editingId === segmentId && editor.text !== committedText
    readonly property bool canSave: sessionActive && segmentId.length > 0 && hasChanges && saveStatus !== "saving"
    signal commitRequested(string segmentId, string text, int revision, string requestId)
    signal draftChanged(string segmentId, string text, int revision)
    signal draftCleared(string segmentId)
    signal applied()
    spacing: 8

    function commitCurrentText() {
        if (!sessionActive || !editingId || saveStatus === "saving" || editor.inputMethodComposing)
            return;
        if (editor.text === committedText) {
            saveStatus = "saved";
            draftCleared(editingId);
            applied();
            return;
        }
        requestId = editingId + ":" + instanceToken + ":" + (++serial);
        pendingText = editor.text;
        saveStatus = "saving";
        errorMessage = "";
        commitRequested(editingId, editor.text, editingRevision, requestId);
    }
    function apply() {
        // Commit an active Vietnamese IME composition before sampling text.
        // Button clicks can otherwise arrive one event ahead of the final
        // composed word, which makes the saved value appear to lose its tail.
        // QInputMethod.commit is available at runtime; Qt's QML type
        // metadata exposes inputMethod only as QObject.
        // qmllint disable missing-property
        if (editor.activeFocus && editor.inputMethodComposing)
            Qt.inputMethod.commit();
        // qmllint enable missing-property
        Qt.callLater(root.commitCurrentText);
    }
    function dismiss() {
        // Finish a composed word before moving to another cue or panel.
        // qmllint disable missing-property
        if (editor.activeFocus && editor.inputMethodComposing)
            Qt.inputMethod.commit();
        // qmllint enable missing-property
        editor.deselect();
        editor.focus = false;
    }
    function restoreDraft(value, version, draftText) {
        installing = true;
        requestId = "";
        pendingText = "";
        editingId = segmentId;
        editingRevision = version;
        committedText = value;
        editor.text = draftText;
        saveStatus = draftText === value ? "saved" : "dirty";
        errorMessage = "";
        installing = false;
    }
    function discard() {
        installing = true;
        editor.text = committedText;
        installing = false;
        saveStatus = "saved";
        errorMessage = "";
        draftCleared(editingId);
    }
    function focusEditor() { editor.forceActiveFocus(); }
    function install() {
        if (editingId === segmentId)
            return;
        installing = true;
        editingId = segmentId;
        editingRevision = revision;
        committedText = savedText;
        editor.text = hasInitialDraft ? initialDraftText : savedText;
        saveStatus = editor.text === committedText ? "saved" : "dirty";
        installing = false;
    }
    onSegmentIdChanged: Qt.callLater(install)
    onRevisionChanged: if (editingId === segmentId) editingRevision = revision
    onSavedTextChanged: {
        if (sessionActive && saveStatus === "saved" && editingId === segmentId
                && !editor.inputMethodComposing) {
            installing = true;
            if (editor.text !== savedText)
                editor.text = savedText;
            committedText = savedText;
            installing = false;
        }
    }
    Component.onCompleted: install()

    ScrollView {
        contentWidth: availableWidth
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.minimumHeight: root.minimumEditorHeight
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        AppTextArea {
            id: editor
            objectName: "manualSubtitleTextInput"
            enabled: root.segmentId.length > 0
            wrapMode: TextEdit.Wrap
            textFormat: TextEdit.PlainText
            selectByMouse: true
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: root.editorFontSize
            padding: Theme.space16
            Accessible.name: qsTr("Nội dung phụ đề")
            background: Rectangle {
                color: Theme.input
                radius: 4
                border.width: editor.keyboardFocus ? 2 : 1
                border.color: editor.keyboardFocus ? Theme.controlFocus
                    : editor.activeFocus ? Theme.outlineStrong : Theme.outline
            }
            onTextChanged: {
                if (!root.installing && root.sessionActive) {
                    root.saveStatus = text === root.committedText ? "saved" : "dirty";
                    if (root.saveStatus === "dirty")
                        root.draftChanged(root.editingId, text, root.editingRevision);
                    else
                        root.draftCleared(root.editingId);
                }
            }
            Keys.onEscapePressed: root.dismiss()
            Keys.onPressed: function(event) {
                if ((event.modifiers & Qt.ControlModifier)
                        && (event.key === Qt.Key_Return || event.key === Qt.Key_Enter)) {
                    root.apply();
                    event.accepted = true;
                }
            }
        }
    }
    Connections {
        target: root.controller
        enabled: root.sessionActive
        function onManualSubtitleSaved(id, version, request) {
            if (id === root.editingId && request === root.requestId) {
                root.committedText = root.pendingText;
                root.editingRevision = version;
                root.errorMessage = "";
                root.saveStatus = editor.text === root.committedText ? "saved" : "dirty";
                if (root.saveStatus === "saved") {
                    root.draftCleared(id);
                    root.applied();
                } else
                    root.draftChanged(id, editor.text, root.editingRevision);
            }
        }
        function onManualSubtitleSaveFailed(id, request, message) {
            if (id === root.editingId && request === root.requestId) {
                root.saveStatus = "error";
                root.errorMessage = String(message || "");
            }
        }
    }
}
