# Unstockfish

This is a Chess Engine project built with Python. The goal is to learn how chess engines work while building one.

## Setup

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -e .[dev]
```

## Run (UCI)

```powershell
python -m unstockfish.uci
```

Or, after installing:

```powershell
unstockfish-uci
```

## Run (CLI)

Analyze a position:

```powershell
unstockfish-cli analyze --depth 6 --fen "r1bq1rk1/ppp2ppp/2n2n2/3pp3/2B1P3/2NP1N2/PPPB1PPP/R2Q1RK1 w - - 0 8"
```

Play against the engine:

```powershell
unstockfish-cli play --engine-side black --depth 4
```

## Run (GUI)

```powershell
unstockfish-gui --depth 6
```

Optional:

```powershell
unstockfish-gui --fen "r1bq1rk1/ppp2ppp/2n2n2/3pp3/2B1P3/2NP1N2/PPPB1PPP/R2Q1RK1 w - - 0 8" --depth 7 --movetime 300
```

## Bench

```powershell
unstockfish-bench --depth 6
```

## Project layout

- src/unstockfish/search.py: negamax + alpha-beta, iterative deepening, quiescence, move ordering
- src/unstockfish/eval.py: material + piece-square tables (tapered MG/EG)
- src/unstockfish/tt.py: transposition table
- src/unstockfish/uci.py: UCI protocol loop
- src/unstockfish/cli.py: simple CLI
- src/unstockfish/gui.py: desktop GUI for play/analyze

## Notes

- Uses python-chess for rules and legality.
- Single-threaded search with time-based stopping.
- Early strength comes from good move ordering and a decent evaluation function.

## Strength roadmap (toward 2200+)

1. Search speed and pruning
   - aspiration windows
   - principal variation search (PVS)
   - null-move pruning
   - late move reductions
2. Evaluation quality
   - mobility
   - pawn structure (isolated/doubled/passed)
   - rook open/semi-open files
   - king shelter terms
3. Time management and tuning
   - better time allocation and panic logic
   - tuning constants via self-play
4. Validation loop
   - tactical regression tests
   - fixed-node and fixed-time self-play checks
