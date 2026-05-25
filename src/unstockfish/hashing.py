from __future__ import annotations

import chess
import chess.polyglot


def position_key(board: chess.Board) -> int:
    key_func = getattr(board, "transposition_key", None)
    if callable(key_func):
        return key_func()
    key_func = getattr(board, "_transposition_key", None)
    if callable(key_func):
        return key_func()
    try:
        return chess.polyglot.zobrist_hash(board)
    except Exception:
        return hash(board.fen())
