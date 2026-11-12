"""Immutable half-open interval lookup, retaining input order for overlaps."""
from bisect import bisect_left


class IntervalIndex:
    def __init__(self, entries):
        rows = [(start, end, order, value) for order, (start, end, value) in enumerate(entries) if end > start]
        rows.sort(key=lambda row: (row[0], row[2]))
        self._rows = rows
        self._starts = [row[0] for row in rows]
        size = 1
        while size < len(rows):
            size *= 2
        self._size = size
        self._ends = [float("-inf")] * (2 * size)
        for index, row in enumerate(rows):
            self._ends[size + index] = row[1]
        for index in range(size - 1, 0, -1):
            self._ends[index] = max(self._ends[index * 2], self._ends[index * 2 + 1])

    def intersect(self, start, end):
        limit = bisect_left(self._starts, end)
        if start >= end or not limit:
            return []
        found = []
        pending = [(1, 0, self._size)]
        while pending:
            node, left, right = pending.pop()
            if left >= limit or self._ends[node] <= start:
                continue
            if right - left == 1:
                row = self._rows[left]
                found.append((row[2], row[3]))
            else:
                middle = (left + right) // 2
                pending.append((node * 2 + 1, middle, right))
                pending.append((node * 2, left, middle))
        found.sort(key=lambda item: item[0])
        return [value for _, value in found]
