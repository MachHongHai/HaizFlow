"""Commit pending IME composition before UI actions consume field text."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickWindow


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
            QEvent.Type.KeyPress,
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
        # ``QInputMethod.commit()`` can synchronously dispatch another Qt
        # event while the original event is still crossing the Python/C++
        # boundary.  Check the re-entry guard *before* touching the nested
        # QEvent.  Calling ``event.type()`` first caused PySide to recursively
        # convert the same native event until the application crashed during
        # Main.qml startup on Windows.
        if self._committing or event is None or event.type() not in self._COMMIT_EVENTS:
            return False
        event_type = event.type()
        pointer_event = event_type in {
            QEvent.Type.MouseButtonPress, QEvent.Type.TabletPress, QEvent.Type.TouchBegin,
        }
        # An application filter sees the same press on the window and again on
        # its QML recipients. Commit once, at the window, not at every recipient.
        if pointer_event and not isinstance(watched, QQuickWindow):
            return False
        focused = self._focused_editor(watched)
        if focused is None:
            return False
        if event_type == QEvent.Type.KeyPress and event.key() not in {
            Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down,
            Qt.Key.Key_Home, Qt.Key.Key_End, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown,
            Qt.Key.Key_Tab, Qt.Key.Key_Backtab, Qt.Key.Key_Return, Qt.Key.Key_Enter,
        }:
            return False
        self._committing = True
        try:
            # Ordinary edits/backspaces and clicks on committed text must not
            # flush the Windows text service. Qt owns that editing transaction.
            if focused.property("inputMethodComposing"):
                self._commit_callback()
            if pointer_event:
                self._dismiss_input_focus(watched, event)
        finally:
            self._committing = False
        return False

    @staticmethod
    def _focused_editor(watched: QObject | None) -> QObject | None:
        focused = watched.activeFocusItem() if isinstance(watched, QQuickWindow) else (
            QGuiApplication.focusObject() if QGuiApplication.instance() else None
        )
        if focused is None or focused.metaObject().indexOfProperty("inputMethodComposing") < 0:
            return None
        return focused

    @staticmethod
    def _dismiss_input_focus(window: QQuickWindow, event: QEvent) -> None:
        """Blur an editable field on outside clicks without consuming the click.

        Run before QML handles the press so another field can subsequently
        receive focus. Keyboard navigation and clicks inside the editor are
        unchanged. Commit pre-edit text before moving focus (see eventFilter).
        """
        focused = window.activeFocusItem()
        if focused is None:
            return
        meta = focused.metaObject()
        if meta.indexOfProperty("cursorPosition") < 0 or meta.indexOfProperty("inputMethodComposing") < 0:
            return
        if event.type() == QEvent.Type.TouchBegin:
            points = event.points()
            if not points:
                return
            position = points[0].position()
        else:
            position = event.position()
        if focused.contains(focused.mapFromScene(position)):
            return
        # QML TextInput/TextEdit expose deselect as a meta-object method.
        from PySide6.QtCore import QMetaObject

        QMetaObject.invokeMethod(focused, "deselect", Qt.ConnectionType.DirectConnection)
        focused.setFocus(False, Qt.FocusReason.MouseFocusReason)
        window.contentItem().forceActiveFocus(Qt.FocusReason.MouseFocusReason)
