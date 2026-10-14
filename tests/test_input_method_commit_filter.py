import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hflow.desktop.input_method_commit_filter import InputMethodCommitFilter


class InputMethodCommitFilterTests(unittest.TestCase):
    def test_commits_only_active_preedit_before_focus_actions(self):
        committed = []
        event_filter = InputMethodCommitFilter(commit_callback=lambda: committed.append(True))

        for event_type in (
            QEvent.Type.FocusAboutToChange,
            QEvent.Type.Close,
            QEvent.Type.WindowDeactivate,
        ):
            with self.subTest(event_type=event_type):
                focused = Mock()
                focused.property.return_value = True
                with patch.object(event_filter, "_focused_editor", return_value=focused):
                    self.assertFalse(event_filter.eventFilter(None, QEvent(event_type)))

        self.assertEqual(len(committed), 3)

    def test_does_not_flush_committed_text_or_forwarded_pointer_events(self):
        committed = []
        event_filter = InputMethodCommitFilter(commit_callback=lambda: committed.append(True))
        focused = Mock()
        focused.property.return_value = False
        with patch.object(event_filter, "_focused_editor", return_value=focused):
            for event_type in event_filter._COMMIT_EVENTS - {QEvent.Type.KeyPress}:
                self.assertFalse(event_filter.eventFilter(None, QEvent(event_type)))
        self.assertEqual(committed, [])

    def test_navigation_finishes_composition_but_edit_keys_do_not(self):
        committed = []
        event_filter = InputMethodCommitFilter(commit_callback=lambda: committed.append(True))
        focused = Mock()
        focused.property.return_value = True
        with patch.object(event_filter, "_focused_editor", return_value=focused):
            for key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Home, Qt.Key_End, Qt.Key_Tab):
                event_filter.eventFilter(None, QKeyEvent(QEvent.Type.KeyPress, key, Qt.NoModifier))
            for key in (Qt.Key_Backspace, Qt.Key_Delete, Qt.Key_A):
                event_filter.eventFilter(None, QKeyEvent(QEvent.Type.KeyPress, key, Qt.NoModifier))
        self.assertEqual(len(committed), 5)

    def test_does_not_commit_for_unrelated_events(self):
        committed = []
        event_filter = InputMethodCommitFilter(commit_callback=lambda: committed.append(True))

        self.assertFalse(event_filter.eventFilter(None, QEvent(QEvent.Type.MouseMove)))
        self.assertFalse(event_filter.eventFilter(None, None))

        self.assertEqual(committed, [])

    def test_reentrant_event_is_ignored_before_inspecting_native_event(self):
        class NestedEvent:
            def type(self):
                raise AssertionError("a nested Qt event must not be inspected while committing")

        nested_event = NestedEvent()
        event_filter = None

        def commit():
            self.assertFalse(event_filter.eventFilter(None, nested_event))

        event_filter = InputMethodCommitFilter(commit_callback=commit)

        focused = Mock()
        focused.property.return_value = True
        with patch.object(event_filter, "_focused_editor", return_value=focused):
            self.assertFalse(event_filter.eventFilter(None, QEvent(QEvent.Type.FocusAboutToChange)))


if __name__ == "__main__":
    unittest.main()
