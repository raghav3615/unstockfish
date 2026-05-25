from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

import chess


class Bound(IntEnum):
    EXACT = 0
    LOWER = 1
    UPPER = 2


@dataclass(frozen=True)
class TTEntry:
    depth: int
    value: int
    bound: Bound
    move: Optional[chess.Move]


class TranspositionTable:
    def __init__(self, size_mb: int = 64) -> None:
        self.set_size_mb(size_mb)
        self.table: dict[int, TTEntry] = {}

    def set_size_mb(self, size_mb: int) -> None:
        self.size_mb = max(1, int(size_mb))
        self.max_entries = max(1024, self.size_mb * 1024 * 1024 // 32)
        if hasattr(self, "table") and len(self.table) > self.max_entries:
            self.table.clear()

    def clear(self) -> None:
        self.table.clear()

    def get(self, key: int) -> Optional[TTEntry]:
        return self.table.get(key)

    def store(self, key: int, depth: int, value: int, bound: Bound, move: Optional[chess.Move]) -> None:
        entry = self.table.get(key)
        if entry is None or depth >= entry.depth or bound == Bound.EXACT:
            self.table[key] = TTEntry(depth, value, bound, move)
        if len(self.table) > self.max_entries:
            self.table.clear()
