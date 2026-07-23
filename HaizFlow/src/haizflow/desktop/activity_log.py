"""Bounded log state for the desktop UI."""

from __future__ import annotations

import os
from collections import deque


class ActivityLogBuffer:
    """Keep a readable tail without repeatedly copying an unbounded log."""

    def __init__(self, *, max_lines: int = 800, max_characters: int = 60_000):
        self._max_lines = max(1, int(max_lines))
        self._max_characters = max(1, int(max_characters))
        self._lines: deque[str] = deque()
        self._character_count = 0

    @property
    def text(self) -> str:
        return "\n".join(self._lines)

    def clear(self) -> None:
        self._lines.clear()
        self._character_count = 0

    def replace(self, text: str) -> None:
        self.clear()
        self.append(text.splitlines())

    def append(self, lines) -> bool:
        added = False
        for line in lines:
            for item in str(line or "").splitlines() or [""]:
                self._lines.append(item)
                self._character_count += len(item) + 1
                added = True
        while self._lines and (
            len(self._lines) > self._max_lines or self._character_count > self._max_characters
        ):
            self._character_count -= len(self._lines.popleft()) + 1
        return added

    @classmethod
    def read_tail(cls, path: str, *, max_characters: int = 60_000) -> str:
        if not path or not os.path.exists(path):
            return ""
        # UTF-8 needs up to four bytes per character. Read a little extra, then
        # decode from the next complete line to avoid rendering a partial entry.
        max_bytes = max(4_096, int(max_characters) * 4)
        with open(path, "rb") as file:
            file.seek(0, os.SEEK_END)
            size = file.tell()
            file.seek(max(0, size - max_bytes))
            data = file.read()
        text = data.decode("utf-8", errors="replace")
        if size > max_bytes:
            _discarded, separator, text = text.partition("\n")
            if not separator:
                return ""
        return text[-max_characters:]
