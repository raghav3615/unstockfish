from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, Callable, Iterable, Optional

import chess

from .constants import DEFAULT_MAX_DEPTH, INF, MATE_SCORE, MATE_THRESHOLD
from .eval import PIECE_VALUES_MG, evaluate
from .hashing import position_key
from .tt import Bound, TranspositionTable

if TYPE_CHECKING:
    from .engine import SearchLimits


InfoCallback = Callable[[int, int, int, int, list[chess.Move]], None]

ASPIRATION_WINDOW = 35
MAX_PLY = 127


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
        self.time_limit: Optional[float] = None
        self.node_limit: Optional[int] = None

        self.killers: list[list[Optional[chess.Move]]] = [[None, None] for _ in range(128)]
        self.history = [[[0 for _ in range(64)] for _ in range(64)] for _ in range(2)]

        self.best_move: Optional[chess.Move] = None
        self.best_score = 0

    def search(self, board: chess.Board, limits: SearchLimits) -> tuple[Optional[chess.Move], int, int, int, list[chess.Move]]:
        self.stop_event.clear()
        self.nodes = 0
        self.best_move = None
        self.best_score = 0
        self.start_time = time.perf_counter()

        self.time_limit = limits.time_ms / 1000.0 if limits.time_ms is not None else None
        self.node_limit = limits.nodes

        max_depth = limits.depth if limits.depth is not None else self.max_depth
        if limits.infinite and limits.depth is None:
            max_depth = self.max_depth

        last_score = 0
        last_pv: list[chess.Move] = []

        for depth in range(1, max_depth + 1):
            if depth == 1:
                score, move = self._negamax_root(board, depth, -INF, INF)
            else:
                window = ASPIRATION_WINDOW
                alpha = max(-INF, last_score - window)
                beta = min(INF, last_score + window)

                while True:
                    score, move = self._negamax_root(board, depth, alpha, beta)
                    if self._should_stop():
                        break
                    if score <= alpha:
                        alpha = max(-INF, score - window)
                        window *= 2
                    elif score >= beta:
                        beta = min(INF, score + window)
                        window *= 2
                    else:
                        break

                    if window > 16000:
                        alpha, beta = -INF, INF

            if self._should_stop():
                break

            if move is not None:
                self.best_move = move
                self.best_score = score
                last_score = score
                last_pv = self._get_pv(board, depth)

            if self.info_callback:
                elapsed_ms = int((time.perf_counter() - self.start_time) * 1000)
                self.info_callback(depth, self.best_score, self.nodes, elapsed_ms, last_pv)

        elapsed_ms = int((time.perf_counter() - self.start_time) * 1000)
        return self.best_move, self.best_score, self.nodes, elapsed_ms, last_pv

    def _should_stop(self) -> bool:
        if self.stop_event.is_set():
            return True

        if self.node_limit is not None and self.nodes >= self.node_limit:
            self.stop_event.set()
            return True

        if self.time_limit is not None and (time.perf_counter() - self.start_time) >= self.time_limit:
            self.stop_event.set()
            return True

        return False

    def _negamax_root(self, board: chess.Board, depth: int, alpha: int, beta: int) -> tuple[int, Optional[chess.Move]]:
        best_score = -INF
        best_move = None

        original_alpha = alpha
        original_beta = beta

        entry = self.tt.get(position_key(board))
        tt_move = entry.move if entry else self.best_move

        moves = list(board.legal_moves)
        if not moves:
            if board.is_check():
                return -MATE_SCORE, None
            return 0, None

        moves.sort(key=lambda m: self._score_move(board, m, tt_move, 0), reverse=True)

        for move_index, move in enumerate(moves):
            if self._should_stop():
                break

            board.push(move)
            if move_index == 0:
                score = -self._negamax(board, depth - 1, -beta, -alpha, 1)
            else:
                score = -self._negamax(board, depth - 1, -alpha - 1, -alpha, 1)
                if score > alpha and score < beta:
                    score = -self._negamax(board, depth - 1, -beta, -alpha, 1)
            board.pop()

            if self._should_stop():
                break

            if score > best_score:
                best_score = score
                best_move = move

            if score > alpha:
                alpha = score
                if alpha >= beta:
                    break

        if best_move is not None and not self._should_stop():
            bound = Bound.EXACT
            if best_score <= original_alpha:
                bound = Bound.UPPER
            elif best_score >= original_beta:
                bound = Bound.LOWER
            self.tt.store(position_key(board), depth, self._to_tt(best_score, 0), bound, best_move)

        return best_score, best_move

    def _negamax(self, board: chess.Board, depth: int, alpha: int, beta: int, ply: int) -> int:
        if self._should_stop():
            return 0

        if ply >= MAX_PLY:
            return evaluate(board)

        self.nodes += 1

        alpha = max(alpha, -MATE_SCORE + ply)
        beta = min(beta, MATE_SCORE - ply - 1)
        if alpha >= beta:
            return alpha

        if depth <= 0:
            return self._qsearch(board, alpha, beta, ply)

        if board.halfmove_clock >= 100 or board.is_repetition(3):
            return 0

        in_check = board.is_check()
        key = position_key(board)
        entry = self.tt.get(key)
        tt_move = entry.move if entry else None

        if entry and entry.depth >= depth:
            value = self._from_tt(entry.value, ply)
            if entry.bound == Bound.EXACT:
                return value
            if entry.bound == Bound.LOWER:
                alpha = max(alpha, value)
            elif entry.bound == Bound.UPPER:
                beta = min(beta, value)
            if alpha >= beta:
                return value

        static_eval = evaluate(board)
        if not in_check:
            if depth <= 2 and static_eval - 120 * depth >= beta:
                return static_eval

            if depth >= 3 and static_eval >= beta and self._has_non_pawn_material(board, board.turn):
                reduction = 2 + depth // 4
                board.push(chess.Move.null())
                score = -self._negamax(board, depth - reduction - 1, -beta, -beta + 1, ply + 1)
                board.pop()
                if self._should_stop():
                    return 0
                if score >= beta:
                    return score

        moves = list(board.legal_moves)
        if not moves:
            if in_check:
                return -MATE_SCORE + ply
            return 0

        moves.sort(key=lambda m: self._score_move(board, m, tt_move, ply), reverse=True)

        best_move = None
        original_alpha = alpha
        original_beta = beta
        side_index = 0 if board.turn == chess.WHITE else 1

        for move_index, move in enumerate(moves):
            is_capture = board.is_capture(move)
            board.push(move)

            child_depth = depth - 1
            if move_index == 0:
                score = -self._negamax(board, child_depth, -beta, -alpha, ply + 1)
            else:
                reduced_depth = child_depth
                if (
                    depth >= 3
                    and not in_check
                    and move_index >= 3
                    and not is_capture
                    and move.promotion is None
                ):
                    reduced_depth = max(1, child_depth - 1)

                score = -self._negamax(board, reduced_depth, -alpha - 1, -alpha, ply + 1)

                if score > alpha and reduced_depth != child_depth:
                    score = -self._negamax(board, child_depth, -alpha - 1, -alpha, ply + 1)

                if score > alpha and score < beta:
                    score = -self._negamax(board, child_depth, -beta, -alpha, ply + 1)

            board.pop()

            if self._should_stop():
                return 0

            if score > alpha:
                alpha = score
                best_move = move
                if alpha >= beta:
                    if not is_capture:
                        self._store_killer(move, ply)
                        self._update_history(side_index, move, depth)
                    break

        if not self._should_stop():
            bound = Bound.EXACT
            if alpha <= original_alpha:
                bound = Bound.UPPER
            elif alpha >= original_beta:
                bound = Bound.LOWER
            self.tt.store(key, depth, self._to_tt(alpha, ply), bound, best_move)

        return alpha

    def _qsearch(self, board: chess.Board, alpha: int, beta: int, ply: int) -> int:
        if self._should_stop():
            return 0

        if ply >= MAX_PLY:
            return evaluate(board)

        self.nodes += 1

        if board.halfmove_clock >= 100 or board.is_repetition(3):
            return 0

        in_check = board.is_check()
        stand_pat = evaluate(board)

        if in_check:
            moves: Iterable[chess.Move] = list(board.legal_moves)
            if not moves:
                return -MATE_SCORE + ply
        else:
            if stand_pat >= beta:
                return beta
            if stand_pat > alpha:
                alpha = stand_pat

            if stand_pat + PIECE_VALUES_MG[chess.QUEEN] < alpha:
                return alpha

            captures = list(board.generate_legal_captures())
            captures.sort(key=lambda m: self._mvv_lva(board, m), reverse=True)
            moves = captures

        for move in moves:
            if not in_check:
                victim = board.piece_type_at(move.to_square)
                if victim is None and board.is_en_passant(move):
                    victim = chess.PAWN
                if victim is not None and stand_pat + PIECE_VALUES_MG[victim] + 150 < alpha:
                    continue

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

        if move.promotion:
            return 95_000 + PIECE_VALUES_MG.get(move.promotion, 0)

        if self.killers[ply][0] == move:
            return 90_000
        if self.killers[ply][1] == move:
            return 80_000

        side_index = 0 if board.turn == chess.WHITE else 1
        return self.history[side_index][move.from_square][move.to_square]

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

    def _has_non_pawn_material(self, board: chess.Board, color: chess.Color) -> bool:
        return bool(board.occupied_co[color] & (board.knights | board.bishops | board.rooks | board.queens))

    def _to_tt(self, value: int, ply: int) -> int:
        if value > MATE_THRESHOLD:
            return value + ply
        if value < -MATE_THRESHOLD:
            return value - ply
        return value

    def _from_tt(self, value: int, ply: int) -> int:
        if value > MATE_THRESHOLD:
            return value - ply
        if value < -MATE_THRESHOLD:
            return value + ply
        return value

    def _get_pv(self, board: chess.Board, depth: int) -> list[chess.Move]:
        pv: list[chess.Move] = []
        probe = board.copy()
        for _ in range(depth):
            entry = self.tt.get(position_key(probe))
            if entry is None or entry.move is None:
                break
            move = entry.move
            if move not in probe.legal_moves:
                break
            pv.append(move)
            probe.push(move)
        return pv
