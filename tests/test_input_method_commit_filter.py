import sys
import unittest
from pathlib import Path

from PySide6.QtCore import QEvent


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.desktop.input_method_commit_filter import InputMethodCommitFilter


class InputMethodCommitFilterTests(unittest.TestCase):
    def test_commits_preedit_before_focus_and_pointer_actions(self):
        committed = []
        event_filter = InputMethodCommitFilter(commit_callback=lambda: committed.append(True))

        for event_type in (
            QEvent.Type.FocusAboutToChange,
            QEvent.Type.Close,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.TabletPress,
            QEvent.Type.TouchBegin,
            QEvent.Type.WindowDeactivate,
        ):
            with self.subTest(event_type=event_type):
                self.assertFalse(event_filter.eventFilter(None, QEvent(event_type)))

        self.assertEqual(len(committed), 6)

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

        self.assertFalse(
            event_filter.eventFilter(None, QEvent(QEvent.Type.FocusAboutToChange))
        )


if __name__ == "__main__":
    unittest.main()
