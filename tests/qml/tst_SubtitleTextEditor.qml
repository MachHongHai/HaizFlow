pragma ComponentBehavior: Bound
import QtQuick
import QtTest
import "../../src/haizflow/desktop/qml"

Item {
    id: root
    width: 800
    height: 600
    QtObject {
        id: controller
        signal manualSubtitleSaved(string id, int version, string request)
        signal manualSubtitleSaveFailed(string id, string request, string message)
    }
    Component {
        id: editorComponent
        SubtitleTextEditor {
            width: 600
            height: 300
            controller: controller
            segmentId: "caption"
            savedText: "Nội dung ban đầu"
        }
    }
    SignalSpy { id: commitSpy; signalName: "commitRequested" }
    SignalSpy { id: appliedSpy; signalName: "applied" }
    TestCase {
        name: "SubtitleTextEditorSaveTests"
        when: windowShown
        function test_twoConsecutiveSavesKeepVietnameseTail() {
            const editor = createTemporaryObject(editorComponent, root);
            verify(!!editor);
            const input = findChild(editor, "manualSubtitleTextInput");
            verify(!!input);
            tryCompare(input, "text", "Nội dung ban đầu");
            commitSpy.target = editor;
            commitSpy.clear();
            input.focus = true;
            input.text = "Và giờ nó đã là của ta!";
            editor.apply();
            tryCompare(commitSpy, "count", 1);
            compare(commitSpy.signalArguments[0][1], "Và giờ nó đã là của ta!");
            controller.manualSubtitleSaved("caption", 1, editor.requestId);
            tryCompare(editor, "saveStatus", "saved");
            input.text = "Thả anh ấy ra, ngay bây giờ.";
            editor.apply();
            tryCompare(commitSpy, "count", 2);
            compare(commitSpy.signalArguments[1][1], "Thả anh ấy ra, ngay bây giờ.");
            controller.manualSubtitleSaved("caption", 2, editor.requestId);
            tryCompare(editor, "committedText", "Thả anh ấy ra, ngay bây giờ.");
        }
        function test_successAndUnchangedApplyBothCompleteDialog() {
            const editor = createTemporaryObject(editorComponent, root);
            verify(!!editor);
            const input = findChild(editor, "manualSubtitleTextInput");
            verify(!!input);
            tryCompare(input, "text", "Nội dung ban đầu");
            appliedSpy.target = editor;
            appliedSpy.clear();
            input.focus = true;
            input.text = "Đã sửa hoàn chỉnh.";
            editor.apply();
            tryCompare(editor, "saveStatus", "saving");
            controller.manualSubtitleSaved("caption", 1, editor.requestId);
            tryCompare(appliedSpy, "count", 1);
            editor.apply();
            tryCompare(appliedSpy, "count", 2);
        }
    }
}
