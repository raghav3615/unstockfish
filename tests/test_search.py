import chess

from unstockfish.engine import Engine, SearchLimits


def test_mate_in_one():
    board = chess.Board("7k/5K2/6Q1/8/8/8/8/8 w - - 0 1")
    engine = Engine()
    result = engine.search(board, SearchLimits(depth=2))
    assert result.best_move is not None
    board.push(result.best_move)
    assert board.is_checkmate()


def test_captures_hanging_queen():
    board = chess.Board("rnb1kbnr/pppp1ppp/8/4p3/3q4/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 3")
    engine = Engine()
    result = engine.search(board, SearchLimits(depth=3))
    assert result.best_move is not None
    assert result.best_move.uci() == "f3d4"


def test_finds_black_mate_in_one():
    board = chess.Board("8/8/8/8/8/6q1/5k2/7K b - - 0 1")
    engine = Engine()
    result = engine.search(board, SearchLimits(depth=2))
    assert result.best_move is not None
    board.push(result.best_move)
    assert board.is_checkmate()


def test_respects_node_limit():
    board = chess.Board()
    engine = Engine()
    result = engine.search(board, SearchLimits(depth=8, nodes=80))
    assert result.best_move is not None
    assert result.nodes <= 100
