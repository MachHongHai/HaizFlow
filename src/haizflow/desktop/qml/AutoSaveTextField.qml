import QtQuick
import "."

StudioField {
    id: root
    property bool edited: false
    property bool committing: false
    signal valueCommitted(string value)

    function commitEdits() {
        if (committing)
            return;
        committing = true;
        // Qt exposes QInputMethod as QObject in the static QML type metadata.
        // qmllint disable missing-property
        Qt.inputMethod.commit();
        // qmllint enable missing-property
        if (edited && !inputMethodComposing) {
            edited = false;
            valueCommitted(text);
        }
        committing = false;
    }

    onTextEdited: edited = true
    onEditingFinished: commitEdits()
    onActiveFocusChanged: if (!activeFocus) commitEdits()
    onInputMethodComposingChanged: if (!inputMethodComposing && !activeFocus) commitEdits()
}
