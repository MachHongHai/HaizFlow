"""Commit pending IME composition before UI actions consume field text."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QGuiApplication


class InputMethodCommitFilter(QObject):
    """Make focus-loss and click handlers observe the final composed text.

    Windows IMEs (including Vietnamese input methods such as Unikey) may keep
    the last word in the pre-edit buffer. QML can emit ``editingFinished`` or a
    button can handle ``clicked`` before that buffer reaches ``TextInput.text``.
    Installing this filter on QApplication commits the buffer while the input
    still owns focus, before the event reaches QML.
    """

    _COMMIT_EVENTS = frozenset(
        {
            QEvent.Type.FocusAboutToChange,
            QEvent.Type.Close,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.TabletPress,
            QEvent.Type.TouchBegin,
            QEvent.Type.WindowDeactivate,
        }
    )

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        commit_callback: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._commit_callback = commit_callback or self._commit_input_method
        self._committing = False

    @staticmethod
    def _commit_input_method() -> None:
        input_method = QGuiApplication.inputMethod()
        if input_method is not None:
            input_method.commit()

    def eventFilter(self, watched: QObject | None, event: QEvent | None) -> bool:  # noqa: N802
        del watched
        if event is None or event.type() not in self._COMMIT_EVENTS or self._committing:
            return False
        self._committing = True
        try:
            self._commit_callback()
        finally:
            self._committing = False
        return False
