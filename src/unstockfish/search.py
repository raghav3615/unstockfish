from __future__ import annotations

import time
import threading
from typing import Callable, Iterable, Optional, TYPE_CHECKING

import chess

from .constants import DEFAULT_MAX_DEPTH, INF, MATE_SCORE
from .eval import evaluate, PIECE_VALUES_MG
from .tt import Bound, TranspositionTable

if TYPE_CHECKING:
    from .engine import SearchLimits


InfoCallback = Callable[[int, int, int, int, list[chess.Move]], None]


class Searcher:
    def __init__(
        self,
        tt: TranspositionTable,
        stop_event: Optional[threading.Event] = None,
        info_callback: Optional[InfoCallback] = None,
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> None:
        self.tt = tt
        self.stop_event = stop_event or threading.Event()
        self.info_callback = info_callback
        self.max_depth = max_depth
        self.nodes = 0
        self.start_time = 0.0
        self.time_limit = None
        self.killers: list[list[Optional[chess.Move]]] = [[None, None] for _ in range(128)]
        self.history = [[[0 for _ in range(64)] for _ in range(64)] for _ in range(2)]
        self.best_move: Optional[chess.Move] = None
        self.best_score = 0

    def search(self, board: chess.Board, limits: SearchLimits) -> tuple[Optional[chess.Move], int, int, int, list[chess.Move]]:
        self.nodes = 0
        self.best_move = None
        self.best_score = 0
        self.start_time = time.perf_counter()
        self.time_limit = limits.time_ms / 1000.0 if limits.time_ms is not None else None

        max_depth = limits.depth if limits.depth is not None else self.max_depth
        if limits.infinite and limits.depth is None:
            max_depth = self.max_depth

        last_pv: list[chess.Move] = []

        for depth in range(1, max_depth + 1):
            score, move = self._negamax_root(board, depth)
            if self._should_stop():
                break
            if move is not None:
                self.best_move = move
                self.best_score = score
                last_pv = self._get_pv(board, depth)

            if self.info_callback:
                elapsed_ms = int((time.perf_counter() - self.start_time) * 1000)
                nps = int(self.nodes * 1000 / max(1, elapsed_ms))
                self.info_callback(depth, self.best_score, self.nodes, elapsed_ms, last_pv)

        elapsed_ms = int((time.perf_counter() - self.start_time) * 1000)
        return self.best_move, self.best_score, self.nodes, elapsed_ms, last_pv

    def _should_stop(self) -> bool:
        if self.stop_event.is_set():
            return True
        if self.time_limit is not None and (time.perf_counter() - self.start_time) >= self.time_limit:
            self.stop_event.set()
            return True
        return False

    def _negamax_root(self, board: chess.Board, depth: int) -> tuple[int, Optional[chess.Move]]:
        alpha = -INF
        beta = INF
        best_score = -INF
        best_move = None

        entry = self.tt.get(board.transposition_key())
        tt_move = entry.move if entry else None

        moves = list(board.legal_moves)
        if not moves:
            if board.is_check():
                return -MATE_SCORE, None
            return 0, None

        moves.sort(key=lambda m: self._score_move(board, m, tt_move, 0), reverse=True)

        for move in moves:
            if self._should_stop():
                break
            board.push(move)
            score = -self._negamax(board, depth - 1, -beta, -alpha, 1)
            board.pop()
            if self._should_stop():
                break
            if score > best_score:
                best_score = score
                best_move = move
            if score > alpha:
                alpha = score

        if best_move is not None and not self._should_stop():
            self.tt.store(
                board.transposition_key(),
                depth,
                best_score,
                Bound.EXACT,
                best_move,
            )

        return best_score, best_move

    def _negamax(self, board: chess.Board, depth: int, alpha: int, beta: int, ply: int) -> int:
        if self._should_stop():
            return 0

        self.nodes += 1

        if depth <= 0:
            return self._qsearch(board, alpha, beta, ply)

        if board.is_repetition(2) or board.can_claim_draw():
            return 0

        key = board.transposition_key()
        entry = self.tt.get(key)
        if entry and entry.depth >= depth:
            if entry.bound == Bound.EXACT:
                return entry.value
            if entry.bound == Bound.LOWER:
                alpha = max(alpha, entry.value)
            elif entry.bound == Bound.UPPER:
                beta = min(beta, entry.value)
            if alpha >= beta:
                return entry.value

        moves = list(board.legal_moves)
        if not moves:
            if board.is_check():
                return -MATE_SCORE + ply
            return 0

        tt_move = entry.move if entry else None
        moves.sort(key=lambda m: self._score_move(board, m, tt_move, ply), reverse=True)

        best_move = None
        original_alpha = alpha
        side_index = 0 if board.turn == chess.WHITE else 1

        for move in moves:
            board.push(move)
            score = -self._negamax(board, depth - 1, -beta, -alpha, ply + 1)
            board.pop()
            if self._should_stop():
                return 0

            if score > alpha:
                alpha = score
                best_move = move
                if alpha >= beta:
                    if not board.is_capture(move):
                        self._store_killer(move, ply)
                        self._update_history(side_index, move, depth)
                    break

        if not self._should_stop():
            bound = Bound.EXACT
            if alpha <= original_alpha:
                bound = Bound.UPPER
            elif alpha >= beta:
                bound = Bound.LOWER
            self.tt.store(key, depth, alpha, bound, best_move)

        return alpha

    def _qsearch(self, board: chess.Board, alpha: int, beta: int, ply: int) -> int:
        if self._should_stop():
            return 0

        self.nodes += 1

        if board.is_checkmate():
            return -MATE_SCORE + ply
        if board.is_stalemate() or board.is_insufficient_material() or board.can_claim_draw():
            return 0

        if board.is_check():
            moves: Iterable[chess.Move] = list(board.legal_moves)
        else:
            stand_pat = evaluate(board)
            if stand_pat >= beta:
                return beta
            if stand_pat > alpha:
                alpha = stand_pat
            moves = board.generate_legal_captures()

        for move in moves:
            board.push(move)
            score = -self._qsearch(board, -beta, -alpha, ply + 1)
            board.pop()
            if self._should_stop():
                return 0
            if score >= beta:
                return beta
            if score > alpha:
                alpha = score

        return alpha

    def _score_move(self, board: chess.Board, move: chess.Move, tt_move: Optional[chess.Move], ply: int) -> int:
        if tt_move and move == tt_move:
            return 1_000_000
        if board.is_capture(move):
            return 100_000 + self._mvv_lva(board, move)
        if self.killers[ply][0] == move:
            return 90_000
        if self.killers[ply][1] == move:
            return 80_000

        side_index = 0 if board.turn == chess.WHITE else 1
        score = self.history[side_index][move.from_square][move.to_square]
        if move.promotion:
            score += 800
        if board.gives_check(move):
            score += 50
        return score

    def _mvv_lva(self, board: chess.Board, move: chess.Move) -> int:
        victim = board.piece_type_at(move.to_square)
        if victim is None and board.is_en_passant(move):
            victim = chess.PAWN
        attacker = board.piece_type_at(move.from_square)
        if victim is None or attacker is None:
            return 0
        return PIECE_VALUES_MG[victim] * 10 - PIECE_VALUES_MG[attacker]

    def _store_killer(self, move: chess.Move, ply: int) -> None:
        if self.killers[ply][0] != move:
            self.killers[ply][1] = self.killers[ply][0]
            self.killers[ply][0] = move

    def _update_history(self, side_index: int, move: chess.Move, depth: int) -> None:
        bonus = depth * depth
        current = self.history[side_index][move.from_square][move.to_square]
        self.history[side_index][move.from_square][move.to_square] = min(current + bonus, 1_000_000)

    def _get_pv(self, board: chess.Board, depth: int) -> list[chess.Move]:
        pv: list[chess.Move] = []
        probe = board.copy()
        for _ in range(depth):
            entry = self.tt.get(probe.transposition_key())
            if entry is None or entry.move is None:
                break
            move = entry.move
            if move not in probe.legal_moves:
                break
            pv.append(move)
            probe.push(move)
        return pv
