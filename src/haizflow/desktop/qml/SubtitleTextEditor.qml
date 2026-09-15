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
    property bool hasInitialDraft: false
    property string initialDraftText: ""
    property string saveStatus: "saved"
    property string editingId: ""
    property int editingRevision: 0
    property string committedText: ""
    property string pendingText: ""
    property bool installing: false
    property int serial: 0
    property string requestId: ""
    property string errorMessage: ""
    property int minimumEditorHeight: 220
    property int editorFontSize: TypeScale.body
    signal commitRequested(string segmentId, string text, int revision, string requestId)
    signal draftChanged(string segmentId, string text, int revision)
    signal draftCleared(string segmentId)
    spacing: 8

    function commitCurrentText() {
        if (!editingId || saveStatus === "saving")
            return;
        if (editor.text === committedText) {
            saveStatus = "saved";
            draftCleared(editingId);
            return;
        }
        requestId = editingId + ":" + (++serial);
        pendingText = editor.text;
        saveStatus = "saving";
        errorMessage = "";
        commitRequested(editingId, editor.text, editingRevision, requestId);
    }
    function apply() {
        // Commit an active Vietnamese IME composition before sampling text.
        // Button clicks can otherwise arrive one event ahead of the final
        // composed word, which makes the saved value appear to lose its tail.
        editor.focus = false;
        commitCurrentText();
    }
    function dismiss() {
        editor.deselect();
        editor.focus = false;
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
        if (saveStatus === "saved" && editingId === segmentId) {
            installing = true;
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
        TextArea {
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
                border.width: 1
                border.color: editor.activeFocus ? Theme.focus : Theme.outline
            }
            onTextChanged: {
                if (!root.installing) {
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
    RowLayout {
        Layout.fillWidth: true
        Layout.preferredHeight: 36
        spacing: Theme.space8

        Rectangle {
            Layout.preferredWidth: 7
            Layout.preferredHeight: 7
            radius: 4
            color: root.saveStatus === "error" ? Theme.danger
                : root.saveStatus === "saving" ? Theme.warning
                : root.saveStatus === "dirty" ? Theme.interactive : Theme.success
        }
        Text {
            color: root.saveStatus === "error" ? Theme.danger : Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.metadata
            text: root.saveStatus === "saving" ? qsTr("Đang lưu…")
                : root.saveStatus === "dirty" ? qsTr("Chưa lưu")
                : root.saveStatus === "error" ? qsTr("Không lưu được") : qsTr("Đã lưu")
        }
        Text {
            text: qsTr("%1 ký tự").arg(editor.length)
            color: Theme.textSubtle
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.metadata
        }
        Text {
            Layout.fillWidth: true
            text: root.errorMessage
            visible: root.errorMessage.length > 0
            color: Theme.danger
            font.family: Theme.fontFamily
            font.pixelSize: TypeScale.metadata
            elide: Text.ElideRight
            textFormat: Text.PlainText
        }
        StudioButton {
            text: qsTr("Bỏ thay đổi")
            variant: "ghost"
            enabled: root.saveStatus === "dirty" || root.saveStatus === "error"
            onClicked: root.discard()
        }
        StudioButton {
            objectName: "manualSubtitleSaveButton"
            text: root.saveStatus === "error" ? qsTr("Thử lưu lại") : qsTr("Lưu thay đổi")
            variant: "primary"
            enabled: root.editingId.length > 0
                && root.saveStatus !== "saving"
                && root.saveStatus !== "saved"
            onClicked: root.apply()
        }
    }
    Connections {
        target: root.controller
        function onManualSubtitleSaved(id, version, request) {
            if (id === root.editingId && request === root.requestId) {
                root.committedText = root.pendingText;
                root.editingRevision = version;
                root.errorMessage = "";
                root.saveStatus = editor.text === root.committedText ? "saved" : "dirty";
                if (root.saveStatus === "saved")
                    root.draftCleared(id);
                else
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
