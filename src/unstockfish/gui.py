from __future__ import annotations

import argparse
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

import chess

from .engine import Engine, SearchLimits, SearchResult


PIECE_SYMBOLS = {
    chess.PAWN: {chess.WHITE: "P", chess.BLACK: "p"},
    chess.KNIGHT: {chess.WHITE: "N", chess.BLACK: "n"},
    chess.BISHOP: {chess.WHITE: "B", chess.BLACK: "b"},
    chess.ROOK: {chess.WHITE: "R", chess.BLACK: "r"},
    chess.QUEEN: {chess.WHITE: "Q", chess.BLACK: "q"},
    chess.KING: {chess.WHITE: "K", chess.BLACK: "k"},
}


class UnstockfishGUI:
    def __init__(self, start_fen: Optional[str], depth: int, movetime: Optional[int]) -> None:
        self.root = tk.Tk()
        self.root.title("Unstockfish")

        self.engine = Engine()
        self.board = chess.Board(start_fen) if start_fen else chess.Board()

        self.square_size = 72
        self.board_pixels = self.square_size * 8
        self.flipped = False
        self.selected_square: Optional[chess.Square] = None
        self.legal_targets: set[chess.Square] = set()
        self.last_move: Optional[chess.Move] = None
        self.thinking = False

        self.engine_side_var = tk.StringVar(value="black")
        self.depth_var = tk.IntVar(value=max(1, depth))
        self.movetime_var = tk.StringVar(value="" if movetime is None else str(max(1, movetime)))
        self.status_var = tk.StringVar(value="Ready")
        self.info_var = tk.StringVar(value="")
        self.fen_var = tk.StringVar(value=self.board.fen())

        self._build_ui()
        self._draw_board()

        self.root.after(200, self._maybe_engine_move)

    def _build_ui(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        main = ttk.Frame(self.root, padding=14)
        main.grid(column=0, row=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main.columnconfigure(0, weight=0)
        main.columnconfigure(1, weight=1)

        self.canvas = tk.Canvas(
            main,
            width=self.board_pixels,
            height=self.board_pixels,
            highlightthickness=0,
            bg="#f1e4c8",
        )
        self.canvas.grid(column=0, row=0, rowspan=10, sticky="nsew")
        self.canvas.bind("<Button-1>", self._on_canvas_click)

        controls = ttk.Frame(main, padding=(14, 0, 0, 0))
        controls.grid(column=1, row=0, sticky="n")

        ttk.Label(controls, text="Unstockfish", font=("Georgia", 16, "bold")).grid(column=0, row=0, sticky="w")

        ttk.Label(controls, text="Engine side").grid(column=0, row=1, sticky="w", pady=(12, 0))
        side_combo = ttk.Combobox(
            controls,
            textvariable=self.engine_side_var,
            values=["black", "white", "none"],
            state="readonly",
            width=10,
        )
        side_combo.grid(column=0, row=2, sticky="w")
        side_combo.bind("<<ComboboxSelected>>", lambda _e: self._maybe_engine_move())

        ttk.Label(controls, text="Depth").grid(column=0, row=3, sticky="w", pady=(12, 0))
        ttk.Spinbox(controls, from_=1, to=30, textvariable=self.depth_var, width=8).grid(column=0, row=4, sticky="w")

        ttk.Label(controls, text="Move time (ms)").grid(column=0, row=5, sticky="w", pady=(12, 0))
        ttk.Entry(controls, textvariable=self.movetime_var, width=12).grid(column=0, row=6, sticky="w")

        button_row = ttk.Frame(controls)
        button_row.grid(column=0, row=7, sticky="w", pady=(14, 0))
        ttk.Button(button_row, text="New Game", command=self._new_game).grid(column=0, row=0, padx=(0, 6), pady=4)
        ttk.Button(button_row, text="Undo", command=self._undo_move).grid(column=1, row=0, padx=(0, 6), pady=4)
        ttk.Button(button_row, text="Flip", command=self._flip_board).grid(column=2, row=0, pady=4)

        button_row2 = ttk.Frame(controls)
        button_row2.grid(column=0, row=8, sticky="w")
        ttk.Button(button_row2, text="Engine Move", command=self._engine_move_now).grid(column=0, row=0, padx=(0, 6), pady=4)
        ttk.Button(button_row2, text="Analyze", command=self._analyze_position).grid(column=1, row=0, pady=4)

        ttk.Label(controls, text="FEN").grid(column=0, row=9, sticky="w", pady=(12, 0))
        fen_entry = ttk.Entry(controls, textvariable=self.fen_var, width=55)
        fen_entry.grid(column=0, row=10, sticky="w")
        ttk.Button(controls, text="Load FEN", command=self._load_fen).grid(column=0, row=11, sticky="w", pady=(6, 0))

        ttk.Label(controls, textvariable=self.status_var, font=("Segoe UI", 10, "bold")).grid(
            column=0,
            row=12,
            sticky="w",
            pady=(12, 0),
        )
        ttk.Label(controls, textvariable=self.info_var, wraplength=420, justify="left").grid(
            column=0,
            row=13,
            sticky="w",
            pady=(6, 0),
        )

    def _new_game(self) -> None:
        if self.thinking:
            return
        self.board.reset()
        self.last_move = None
        self.selected_square = None
        self.legal_targets.clear()
        self.fen_var.set(self.board.fen())
        self.status_var.set("New game")
        self.info_var.set("")
        self._draw_board()
        self._maybe_engine_move()

    def _undo_move(self) -> None:
        if self.thinking or not self.board.move_stack:
            return
        self.board.pop()
        if self.board.move_stack and self._is_engine_side(self.board.turn):
            self.board.pop()
        self.last_move = self.board.move_stack[-1] if self.board.move_stack else None
        self.selected_square = None
        self.legal_targets.clear()
        self.fen_var.set(self.board.fen())
        self.status_var.set("Move undone")
        self._draw_board()

    def _flip_board(self) -> None:
        self.flipped = not self.flipped
        self._draw_board()

    def _load_fen(self) -> None:
        if self.thinking:
            return
        fen = self.fen_var.get().strip()
        try:
            self.board.set_fen(fen)
        except ValueError:
            messagebox.showerror("Invalid FEN", "Could not parse this FEN string.")
            return
        self.last_move = None
        self.selected_square = None
        self.legal_targets.clear()
        self.status_var.set("Position loaded")
        self.info_var.set("")
        self._draw_board()
        self._maybe_engine_move()

    def _on_canvas_click(self, event: tk.Event) -> None:
        if self.thinking or self.board.is_game_over() or self._is_engine_side(self.board.turn):
            return

        square = self._event_to_square(event.x, event.y)
        if square is None:
            return

        if self.selected_square is None:
            piece = self.board.piece_at(square)
            if piece is None or piece.color != self.board.turn:
                return
            self.selected_square = square
            self.legal_targets = {
                move.to_square for move in self.board.legal_moves if move.from_square == self.selected_square
            }
            self._draw_board()
            return

        if square == self.selected_square:
            self.selected_square = None
            self.legal_targets.clear()
            self._draw_board()
            return

        move = self._pick_move(self.selected_square, square)
        self.selected_square = None
        self.legal_targets.clear()
        if move is None:
            self._draw_board()
            return

        self.board.push(move)
        self.last_move = move
        self.fen_var.set(self.board.fen())
        self._draw_board()

        if self.board.is_game_over():
            self._set_game_over_status()
            return
        self._maybe_engine_move()

    def _pick_move(self, from_square: chess.Square, to_square: chess.Square) -> Optional[chess.Move]:
        candidates = [
            move
            for move in self.board.legal_moves
            if move.from_square == from_square and move.to_square == to_square
        ]
        if not candidates:
            return None

        promotions = [move for move in candidates if move.promotion is not None]
        if promotions:
            for move in promotions:
                if move.promotion == chess.QUEEN:
                    return move
            return promotions[0]

        return candidates[0]

    def _engine_move_now(self) -> None:
        if self.thinking or self.board.is_game_over():
            return
        self._start_search(apply_move=True)

    def _analyze_position(self) -> None:
        if self.thinking:
            return
        self._start_search(apply_move=False)

    def _maybe_engine_move(self) -> None:
        if self.thinking or self.board.is_game_over():
            if self.board.is_game_over():
                self._set_game_over_status()
            return
        if self._is_engine_side(self.board.turn):
            self._start_search(apply_move=True)

    def _start_search(self, apply_move: bool) -> None:
        depth = max(1, int(self.depth_var.get()))
        movetime_text = self.movetime_var.get().strip()
        movetime = int(movetime_text) if movetime_text else None
        if movetime is not None:
            movetime = max(1, movetime)

        limits = SearchLimits(depth=depth, time_ms=movetime)
        board_snapshot = self.board.copy()
        self.thinking = True
        self.status_var.set("Engine thinking...")
        self.info_var.set("")

        def worker() -> None:
            result = self.engine.search(board_snapshot, limits)
            self.root.after(0, lambda: self._finish_search(result, board_snapshot, apply_move))

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def _finish_search(self, result: SearchResult, board_snapshot: chess.Board, apply_move: bool) -> None:
        self.thinking = False

        best = result.best_move.uci() if result.best_move is not None else "0000"
        pv = " ".join(move.uci() for move in result.pv)
        self.info_var.set(f"bestmove {best} | score {result.score} | nodes {result.nodes} | pv {pv}")

        if apply_move and result.best_move is not None and self.board.fen() == board_snapshot.fen():
            if result.best_move in self.board.legal_moves:
                self.board.push(result.best_move)
                self.last_move = result.best_move
                self.fen_var.set(self.board.fen())
                self._draw_board()

        if self.board.is_game_over():
            self._set_game_over_status()
        else:
            self.status_var.set("Ready")

    def _is_engine_side(self, side_to_move: chess.Color) -> bool:
        mode = self.engine_side_var.get()
        if mode == "none":
            return False
        if mode == "white":
            return side_to_move == chess.WHITE
        return side_to_move == chess.BLACK

    def _set_game_over_status(self) -> None:
        outcome = self.board.outcome(claim_draw=True)
        if outcome is None:
            self.status_var.set("Game over")
            return
        winner = "White" if outcome.winner is chess.WHITE else "Black" if outcome.winner is chess.BLACK else "None"
        self.status_var.set(f"Game over: {self.board.result()} (winner: {winner})")

    def _draw_board(self) -> None:
        self.canvas.delete("all")

        light = "#f2e6cf"
        dark = "#a97847"
        selected = "#e7c65b"
        target = "#d8b46d"
        last = "#8ab97f"

        for display_rank in range(8):
            for display_file in range(8):
                square = self._display_to_square(display_file, display_rank)
                x1 = display_file * self.square_size
                y1 = display_rank * self.square_size
                x2 = x1 + self.square_size
                y2 = y1 + self.square_size

                color = light if (display_file + display_rank) % 2 == 0 else dark
                if self.last_move and square in {self.last_move.from_square, self.last_move.to_square}:
                    color = last
                if self.selected_square == square:
                    color = selected
                elif square in self.legal_targets:
                    color = target

                self.canvas.create_rectangle(x1, y1, x2, y2, fill=color, outline=color)

                piece = self.board.piece_at(square)
                if piece is None:
                    continue
                symbol = PIECE_SYMBOLS[piece.piece_type][piece.color]
                piece_color = "#121212" if piece.color == chess.BLACK else "#fbfbfb"
                self.canvas.create_text(
                    (x1 + x2) // 2,
                    (y1 + y2) // 2,
                    text=symbol,
                    fill=piece_color,
                    font=("Segoe UI Symbol", 40),
                )

    def _event_to_square(self, x: int, y: int) -> Optional[chess.Square]:
        display_file = x // self.square_size
        display_rank = y // self.square_size
        if display_file < 0 or display_file > 7 or display_rank < 0 or display_rank > 7:
            return None
        return self._display_to_square(display_file, display_rank)

    def _display_to_square(self, display_file: int, display_rank: int) -> chess.Square:
        if self.flipped:
            board_file = 7 - display_file
            board_rank = display_rank
        else:
            board_file = display_file
            board_rank = 7 - display_rank
        return chess.square(board_file, board_rank)

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Unstockfish desktop GUI")
    parser.add_argument("--fen", default=None, help="Initial FEN")
    parser.add_argument("--depth", type=int, default=6, help="Search depth")
    parser.add_argument("--movetime", type=int, default=None, help="Time limit per move in ms")
    args = parser.parse_args()

    gui = UnstockfishGUI(start_fen=args.fen, depth=args.depth, movetime=args.movetime)
    gui.run()


if __name__ == "__main__":
    main()
