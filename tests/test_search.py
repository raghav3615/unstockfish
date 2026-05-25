import chess

from unstockfish.engine import Engine, SearchLimits


def test_mate_in_one():
    board = chess.Board("7k/5K2/6Q1/8/8/8/8/8 w - - 0 1")
    engine = Engine()
    result = engine.search(board, SearchLimits(depth=2))
    assert result.best_move is not None
    board.push(result.best_move)
    assert board.is_checkmate()
