pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtTest
import "../../src/haizflow/desktop/qml"

Item {
    id: root
    width: 720
    height: 650
    Component { id: scopeComponent; ManualVoiceScope { width: 500 } }
    TestCase {
        name: "ManualVoiceScopeTests"
        when: windowShown
        function rows() { return [
            {segment_id: "a", text: "Xin chào.", start: 3.15, end: 5.4},
            {segment_id: "b", text: "Cảm ơn mẹ.", start: 8.4, end: 10.125},
            {segment_id: "c", text: "Chúc ngủ ngon.", start: 12, end: 14}
        ]; }
        function test_defaultAndCurrentSentence() {
            const scope = createTemporaryObject(scopeComponent, root);
            scope.reset(rows(), "b");
            compare(scope.scope, "all");
            compare(scope.valid, true);
            compare(scope.targetIds().length, 0);
            scope.scope = "segment";
            compare(scope.targetIds()[0], "b");
            compare(findChild(scope, "manualVoiceCurrentCueText").text, "Cảm ơn mẹ.");
            compare(findChild(scope, "manualVoiceCurrentCueTime").text, "02  00:08.400 — 00:10.125");
            scope.currentSegmentId = "missing";
            compare(scope.valid, false);
            scope.reset(rows(), "");
            scope.scope = "segment";
            compare(scope.valid, false);
            compare(findChild(scope, "manualVoiceCurrentCueText").visible, false);
        }
        function test_chooseSeveralWithPointerAndKeyboard() {
            const scope = createTemporaryObject(scopeComponent, root);
            scope.reset(rows(), "b");
            scope.scope = "selection";
            tryVerify(function() { return !!findChild(scope, "subtitleCue_0"); });
            const first = findChild(scope, "subtitleCue_0");
            compare(findChild(scope, "subtitleCueTime_0").text, "00:03.150 — 00:05.400");
            mouseClick(first, 150, 30);
            compare(scope.selectedIds.length, 2);
            compare(first.checked, true);
            first.forceActiveFocus();
            keyClick(Qt.Key_Space);
            compare(scope.selectedIds.length, 1);
            compare(first.checked, false);
            mouseClick(findChild(scope, "subtitleCueCheck_0"), 9, 15);
            compare(scope.selectedIds.length, 2);
            compare(first.checked, true);
            scope.selectedIds = ["b"];
            compare(first.checked, false);
            compare(findChild(scope, "subtitleCueCheck_0").checked, false);
            mouseClick(findChild(scope, "subtitleCue_1"), 150, 30);
            compare(scope.valid, false);
            scope.reset(rows(), "c");
            compare(scope.selectedIds[0], "c");
        }
        function test_searchKeepsSelectionAndSourceTimeline() {
            const scope = createTemporaryObject(scopeComponent, root);
            scope.reset(rows(), "a");
            scope.scope = "selection";
            const search = findChild(scope, "subtitleCueSearch");
            search.text = "ngủ ngon";
            search.forceActiveFocus();
            keyClick(Qt.Key_Return);
            const list = findChild(scope, "manualVoiceSentenceList");
            tryCompare(list, "selectedIndex", 2);
            compare(scope.selectedIds[0], "a");
            compare(scope.selectedIds.length, 1);
            scope.reset(rows(), "b");
            compare(search.text, "");
        }
        function test_scopeDropdownClosesOnSecondClick() {
            const scope = createTemporaryObject(scopeComponent, root);
            scope.reset(rows(), "a");
            const combo = findChild(scope, "manualVoiceScope");
            mouseClick(combo, 30, 20);
            tryCompare(combo.popup, "opened", true);
            mouseClick(combo, 30, 20);
            tryCompare(combo.popup, "visible", false);
        }
    }
}
