from __future__ import annotations

import sys
import threading
from typing import Optional

import chess

from .constants import MATE_SCORE, MATE_THRESHOLD
from .engine import Engine, SearchLimits, SearchResult


class UCIController:
    def __init__(self) -> None:
        self.engine = Engine()
        self.board = chess.Board()
        self.search_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.last_result: Optional[SearchResult] = None
        self.bestmove_sent = False

    def loop(self) -> None:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            tokens = line.split()
            cmd = tokens[0]

            if cmd == "uci":
                self._handle_uci()
            elif cmd == "isready":
                print("readyok", flush=True)
            elif cmd == "setoption":
                self._handle_setoption(tokens)
            elif cmd == "ucinewgame":
                self.engine.new_game()
                self.board.reset()
            elif cmd == "position":
                self._handle_position(tokens)
            elif cmd == "go":
                self._handle_go(tokens)
            elif cmd == "stop":
                self._stop_search()
            elif cmd == "quit":
                self._stop_search()
                break

    def _handle_uci(self) -> None:
        print("id name Unstockfish", flush=True)
        print("id author You", flush=True)
        print("option name Hash type spin default 64 min 1 max 1024", flush=True)
        print("uciok", flush=True)

    def _handle_setoption(self, tokens: list[str]) -> None:
        if "name" not in tokens:
            return
        name_index = tokens.index("name") + 1
        if name_index >= len(tokens):
            return
        name = tokens[name_index].lower()
        if name != "hash":
            return
        if "value" not in tokens:
            return
        value_index = tokens.index("value") + 1
        if value_index >= len(tokens):
            return
        try:
            size_mb = int(tokens[value_index])
        except ValueError:
            return
        self.engine.set_hash_mb(size_mb)

    def _handle_position(self, tokens: list[str]) -> None:
        if len(tokens) < 2:
            return

        move_tokens: list[str] = []
        if "moves" in tokens:
            moves_index = tokens.index("moves")
            move_tokens = tokens[moves_index + 1 :]
            pos_tokens = tokens[1:moves_index]
        else:
            pos_tokens = tokens[1:]

        if not pos_tokens:
            return

        if pos_tokens[0] == "startpos":
            self.board.reset()
        elif pos_tokens[0] == "fen":
            fen = " ".join(pos_tokens[1:])
            try:
                self.board.set_fen(fen)
            except ValueError:
                return

        for mv in move_tokens:
            try:
                self.board.push_uci(mv)
            except ValueError:
                break

    def _handle_go(self, tokens: list[str]) -> None:
        depth = None
        movetime = None
        nodes = None
        wtime = None
        btime = None
        winc = 0
        binc = 0
        movestogo = None
        infinite = False

        i = 1
        while i < len(tokens):
            t = tokens[i]
            if t == "depth" and i + 1 < len(tokens):
                depth = int(tokens[i + 1])
                i += 2
            elif t == "movetime" and i + 1 < len(tokens):
                movetime = int(tokens[i + 1])
                i += 2
            elif t == "nodes" and i + 1 < len(tokens):
                nodes = int(tokens[i + 1])
                i += 2
            elif t == "wtime" and i + 1 < len(tokens):
                wtime = int(tokens[i + 1])
                i += 2
            elif t == "btime" and i + 1 < len(tokens):
                btime = int(tokens[i + 1])
                i += 2
            elif t == "winc" and i + 1 < len(tokens):
                winc = int(tokens[i + 1])
                i += 2
            elif t == "binc" and i + 1 < len(tokens):
                binc = int(tokens[i + 1])
                i += 2
            elif t == "movestogo" and i + 1 < len(tokens):
                movestogo = int(tokens[i + 1])
                i += 2
            elif t == "infinite":
                infinite = True
                i += 1
            else:
                i += 1

        time_ms = movetime
        if time_ms is None:
            time_ms = self._compute_time_ms(wtime, btime, winc, binc, movestogo)

        if depth is None and time_ms is None and not infinite:
            depth = 6

        limits = SearchLimits(depth=depth, time_ms=time_ms, nodes=nodes, infinite=infinite)
        self._start_search(limits)

    def _compute_time_ms(
        self,
        wtime: Optional[int],
        btime: Optional[int],
        winc: int,
        binc: int,
        movestogo: Optional[int],
    ) -> Optional[int]:
        remaining = wtime if self.board.turn == chess.WHITE else btime
        inc = winc if self.board.turn == chess.WHITE else binc
        if remaining is None:
            return None
        if movestogo:
            base = remaining / max(1, movestogo)
        else:
            base = remaining / 30
        base += inc * 0.7
        return max(10, int(base))

    def _start_search(self, limits: SearchLimits) -> None:
        self._stop_search(send_bestmove=False)
        self.stop_event = threading.Event()
        self.bestmove_sent = False

        def run_search() -> None:
            result = self.engine.search(
                self.board.copy(),
                limits,
                stop_event=self.stop_event,
                info_callback=self._info_callback,
            )
            with self.lock:
                self.last_result = result
                if not self.bestmove_sent:
                    self._send_bestmove(result)

        self.search_thread = threading.Thread(target=run_search, daemon=True)
        self.search_thread.start()

    def _stop_search(self, send_bestmove: bool = True) -> None:
        if self.search_thread and self.search_thread.is_alive():
            self.stop_event.set()
            self.search_thread.join()
        if send_bestmove and self.last_result and not self.bestmove_sent:
            self._send_bestmove(self.last_result)

    def _send_bestmove(self, result: SearchResult) -> None:
        self.bestmove_sent = True
        if result.best_move is None:
            print("bestmove 0000", flush=True)
        else:
            print(f"bestmove {result.best_move.uci()}", flush=True)

    def _info_callback(self, depth: int, score: int, nodes: int, time_ms: int, pv: list[chess.Move]) -> None:
        score_str = self._format_score(score)
        nps = int(nodes * 1000 / max(1, time_ms))
        pv_str = " ".join(move.uci() for move in pv)
        print(
            f"info depth {depth} {score_str} nodes {nodes} nps {nps} time {time_ms} pv {pv_str}",
            flush=True,
        )

    def _format_score(self, score: int) -> str:
        if abs(score) >= MATE_THRESHOLD:
            mate = (MATE_SCORE - abs(score) + 1) // 2
            if score < 0:
                mate = -mate
            return f"score mate {mate}"
        return f"score cp {score}"


def main() -> None:
    controller = UCIController()
    controller.loop()


if __name__ == "__main__":
    main()
