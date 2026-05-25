from __future__ import annotations

import argparse
from typing import Optional

import chess

from .engine import Engine, SearchLimits


def _parse_move(board: chess.Board, text: str) -> Optional[chess.Move]:
    text = text.strip()
    if not text:
        return None
    try:
        return board.parse_san(text)
    except ValueError:
        pass
    try:
        return board.parse_uci(text)
    except ValueError:
        return None


def _analyze(args: argparse.Namespace) -> int:
    board = chess.Board(args.fen) if args.fen else chess.Board()
    engine = Engine()
    limits = SearchLimits(depth=args.depth, time_ms=args.movetime)
    result = engine.search(board, limits)

    move = result.best_move.uci() if result.best_move else "0000"
    pv = " ".join(m.uci() for m in result.pv)
    print(f"bestmove {move}")
    if pv:
        print(f"pv {pv}")
    print(f"score {result.score} nodes {result.nodes} time {result.time_ms}ms")
    return 0


def _play(args: argparse.Namespace) -> int:
    board = chess.Board()
    engine = Engine()

    engine_side = args.engine_side
    if engine_side == "random":
        engine_side = "white" if board.turn == chess.WHITE else "black"

    while not board.is_game_over():
        print(board)
        print()

        if (board.turn == chess.WHITE and engine_side == "white") or (
            board.turn == chess.BLACK and engine_side == "black"
        ):
            limits = SearchLimits(depth=args.depth, time_ms=args.movetime)
            result = engine.search(board, limits)
            move = result.best_move
            if move is None:
                print("Engine has no moves.")
                break
            print(f"Engine plays: {move.uci()}")
            board.push(move)
            continue

        user_input = input("Your move (SAN or UCI, or 'quit'): ").strip()
        if user_input.lower() in {"quit", "exit"}:
            break
        move = _parse_move(board, user_input)
        if move is None:
            print("Invalid move. Try again.")
            continue
        board.push(move)

    print(board)
    print()
    print(f"Game over: {board.result()}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Unstockfish CLI")
    subparsers = parser.add_subparsers(dest="command")

    analyze = subparsers.add_parser("analyze", help="Analyze a position")
    analyze.add_argument("--fen", help="FEN string", default=None)
    analyze.add_argument("--depth", type=int, default=6)
    analyze.add_argument("--movetime", type=int, default=None, help="Time limit in ms")
    analyze.set_defaults(func=_analyze)

    play = subparsers.add_parser("play", help="Play against the engine")
    play.add_argument("--engine-side", choices=["white", "black", "random"], default="black")
    play.add_argument("--depth", type=int, default=4)
    play.add_argument("--movetime", type=int, default=None, help="Time limit in ms")
    play.set_defaults(func=_play)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
