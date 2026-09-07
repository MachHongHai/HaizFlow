"""Application edit history, kept strictly separate from route navigation."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import Property, QObject, Signal, Slot


@dataclass
class _EditCommand:
    label: str
    undo: Callable[[], bool]
    redo: Callable[[], bool]
    merge_key: str = ""


class AppEditHistory(QObject):
    changed = Signal()

    def __init__(self, parent=None, *, limit: int = 100):
        super().__init__(parent)
        self._undo: list[_EditCommand] = []
        self._redo: list[_EditCommand] = []
        self._contexts: dict[str, tuple[list[_EditCommand], list[_EditCommand]]] = {}
        self._limit = max(10, int(limit))
        self._replaying = False
        self._context_id = ""

    @Property(bool, notify=changed)
    def canUndo(self) -> bool:
        return bool(self._undo)

    @Property(bool, notify=changed)
    def canRedo(self) -> bool:
        return bool(self._redo)

    @Property(str, notify=changed)
    def undoLabel(self) -> str:
        return self._undo[-1].label if self._undo else ""

    @Property(str, notify=changed)
    def redoLabel(self) -> str:
        return self._redo[-1].label if self._redo else ""

    @property
    def replaying(self) -> bool:
        return self._replaying

    def select_context(self, context_id: str) -> None:
        context_id = str(context_id or "")
        if context_id == self._context_id:
            return
        if self._context_id:
            self._contexts[self._context_id] = (self._undo, self._redo)
        self._context_id = context_id
        self._undo, self._redo = self._contexts.pop(context_id, ([], []))
        self.changed.emit()

    def select_video(self, video_id: str) -> None:
        self.select_context(f"video:{video_id}" if video_id else "")

    def record(
        self,
        label: str,
        undo: Callable[[], bool],
        redo: Callable[[], bool],
        *,
        merge_key: str = "",
        context_id: str = "",
    ) -> None:
        target_context = str(context_id or self._context_id)
        if self._replaying or not target_context:
            return
        command = _EditCommand(str(label), undo, redo, str(merge_key))
        if target_context == self._context_id:
            undo_stack, redo_stack = self._undo, self._redo
        else:
            undo_stack, redo_stack = self._contexts.setdefault(target_context, ([], []))
        if merge_key and undo_stack and undo_stack[-1].merge_key == merge_key:
            previous = undo_stack[-1]
            undo_stack[-1] = _EditCommand(command.label, previous.undo, command.redo, command.merge_key)
        else:
            undo_stack.append(command)
            del undo_stack[:-self._limit]
        redo_stack.clear()
        if target_context == self._context_id:
            self.changed.emit()

    @Slot(result=bool)
    def undo(self) -> bool:
        if not self._undo:
            return False
        command = self._undo[-1]
        self._replaying = True
        try:
            accepted = bool(command.undo())
        finally:
            self._replaying = False
        if not accepted:
            return False
        self._undo.pop()
        self._redo.append(command)
        self.changed.emit()
        return True

    @Slot(result=bool)
    def redo(self) -> bool:
        if not self._redo:
            return False
        command = self._redo[-1]
        self._replaying = True
        try:
            accepted = bool(command.redo())
        finally:
            self._replaying = False
        if not accepted:
            return False
        self._redo.pop()
        self._undo.append(command)
        self.changed.emit()
        return True

    @Slot()
    def clear(self) -> None:
        if not self._undo and not self._redo:
            return
        self._undo.clear()
        self._redo.clear()
        self.changed.emit()


# Compatibility for code and third-party integrations that imported the
# Manual-only name during the schema-v17 transition.
ManualEditHistory = AppEditHistory
