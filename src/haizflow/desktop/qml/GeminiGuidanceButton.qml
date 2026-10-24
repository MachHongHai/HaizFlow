pragma ComponentBehavior: Bound
import QtQuick
import "."

StudioButton {
    id: root
    property string instructions: ""
    property string glossary: ""
    property string translationStyle: "balanced"
    property var saveHandler: null
    property string contextKey: AppController.projectKey + ":" + AppController.selectedVideoId
    signal guidanceEdited(string instructions, string glossary, string style)
    text: qsTr("Văn phong & hướng dẫn")
    iconName: "edit"
    onClicked: editorLoader.invoke("openForGuidance", [root.instructions, root.glossary, root.contextKey, root.translationStyle])
    onContextKeyChanged: editorLoader.release()

    LazyDialogLoader {
        id: editorLoader
        sourceComponent: Component {
            GeminiGuidanceDialog {
                id: dialog
                objectName: "geminiGuidanceDialog"
                onConfirmed: function(instructions, glossary, owner, style) {
                    if (owner !== root.contextKey || !root.enabled)
                        return;
                    if (root.saveHandler !== null) {
                        if (root.saveHandler(instructions, glossary, style))
                            dialog.close();
                    } else {
                        root.guidanceEdited(instructions, glossary, style);
                        dialog.close();
                    }
                }
                onClosed: editorLoader.release()
            }
        }
    }
}
