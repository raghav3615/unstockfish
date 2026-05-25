from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import chess

from .search import InfoCallback, Searcher
from .tt import TranspositionTable


@dataclass(slots=True)
class SearchLimits:
    depth: Optional[int] = None
    time_ms: Optional[int] = None
    nodes: Optional[int] = None
    infinite: bool = False


@dataclass(slots=True)
class SearchResult:
    best_move: Optional[chess.Move]
    score: int
    depth: int
    nodes: int
    time_ms: int
    pv: list[chess.Move]


class Engine:
    def __init__(self, hash_mb: int = 64) -> None:
        self.tt = TranspositionTable(hash_mb)

    def set_hash_mb(self, size_mb: int) -> None:
        self.tt.set_size_mb(size_mb)

    def new_game(self) -> None:
        self.tt.clear()

    def search(
        self,
        board: chess.Board,
        limits: SearchLimits,
        stop_event=None,
        info_callback: Optional[InfoCallback] = None,
    ) -> SearchResult:
        searcher = Searcher(self.tt, stop_event=stop_event, info_callback=info_callback)
        best_move, score, nodes, time_ms, pv = searcher.search(board, limits)
        depth = limits.depth if limits.depth is not None else len(pv)
        return SearchResult(
            best_move=best_move,
            score=score,
            depth=depth,
            nodes=nodes,
            time_ms=time_ms,
            pv=pv,
        )
