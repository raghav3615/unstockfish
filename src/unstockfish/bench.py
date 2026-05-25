from __future__ import annotations

import argparse
import time

import chess

from .engine import Engine, SearchLimits

BENCH_POSITIONS = [
    "r1bq1rk1/ppp2ppp/2n2n2/3pp3/2B1P3/2NP1N2/PPPB1PPP/R2Q1RK1 w - - 0 8",
    "r2q1rk1/pp2bppp/2n1pn2/2pp4/3P4/1P1BPN2/PB1N1PPP/R2Q1RK1 w - - 0 9",
    "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/2N5/PPPP1PPP/R1BQKBNR w KQkq - 2 3",
    "r3k2r/pp1n1ppp/2p1bn2/q2p4/3P4/1P1BPN2/PB1N1PPP/R2Q1RK1 w kq - 0 10",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Unstockfish benchmark")
    parser.add_argument("--depth", type=int, default=6)
    parser.add_argument("--movetime", type=int, default=None, help="Time limit per position in ms")
    args = parser.parse_args()

    engine = Engine()
    start = time.perf_counter()
    total_nodes = 0

    for fen in BENCH_POSITIONS:
        board = chess.Board(fen)
        limits = SearchLimits(depth=args.depth, time_ms=args.movetime)
        result = engine.search(board, limits)
        total_nodes += result.nodes
        best = result.best_move.uci() if result.best_move else "0000"
        print(f"{fen} -> {best} ({result.nodes} nodes, {result.time_ms}ms)")

    elapsed = max(0.001, time.perf_counter() - start)
    nps = int(total_nodes / elapsed)
    print(f"Total nodes: {total_nodes}")
    print(f"Elapsed: {elapsed:.2f}s")
    print(f"Nodes/sec: {nps}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
