"""Persistence in known formats.

- Per-game moves + clock times -> standard PGN with ``[%clk H:MM:SS]`` comments.
- Games index -> ``data/games.csv`` (one row per finished game).
- Full per-move + per-game report -> ``data/reports/<id>.json``.
"""

from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path

import chess
import chess.pgn

from .clock import format_clock
from .models import GameConfig, GameResult, MoveRecord

DATA_DIR = Path(os.environ.get("CHESS_DATA_DIR", "data"))
PGN_DIR = DATA_DIR / "pgn"
REPORTS_DIR = DATA_DIR / "reports"
GAMES_CSV = DATA_DIR / "games.csv"

CSV_COLUMNS = [
    "game_id",
    "date",
    "white_model",
    "black_model",
    "result",
    "winner_model",
    "termination",
    "total_moves",
    "time_control",
    "white_clock_end",
    "black_clock_end",
    "duration_sec",
    "white_moves",
    "black_moves",
    "white_think_sec",
    "black_think_sec",
    "total_input_tokens",
    "total_output_tokens",
    "total_cost_usd",
    "white_cost_usd",
    "black_cost_usd",
    "white_retries",
    "black_retries",
    "total_retries",
    "pgn_path",
    "report_path",
]


def ensure_dirs() -> None:
    PGN_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def build_pgn(
    config: GameConfig,
    result: GameResult,
    moves: list[MoveRecord],
) -> str:
    """Render a PGN string with standard headers and per-move ``%clk`` comments."""
    game = chess.pgn.Game()
    game.headers["Event"] = config.event
    game.headers["Site"] = "Chess Blitz AI"
    game.headers["Date"] = result.date.split("T")[0].replace("-", ".")
    game.headers["Round"] = "-"
    game.headers["White"] = result.white_model
    game.headers["Black"] = result.black_model
    game.headers["Result"] = result.result
    game.headers["TimeControl"] = result.time_control
    game.headers["Termination"] = result.termination

    node = game
    for mv in moves:
        move = chess.Move.from_uci(mv.uci)
        node = node.add_variation(move)
        mover_clock = mv.white_clock if mv.color == "white" else mv.black_clock
        node.comment = f"[%clk {format_clock(mover_clock)}]"

    exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=True)
    return game.accept(exporter)


def save_game(
    config: GameConfig,
    result: GameResult,
    moves: list[MoveRecord],
) -> None:
    """Write PGN + report JSON, and append the CSV index row."""
    ensure_dirs()

    # PGN
    Path(result.pgn_path).write_text(build_pgn(config, result, moves), encoding="utf-8")

    # Report JSON (per-game + per-move)
    report = {
        "game": result.model_dump(),
        "config": {
            "base_seconds": config.base_seconds,
            "increment_seconds": config.increment_seconds,
            "time_control": config.time_control_str,
        },
        "moves": [m.model_dump() for m in moves],
    }
    Path(result.report_path).write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )

    # CSV index (append; write header if new)
    write_header = not GAMES_CSV.exists()
    with GAMES_CSV.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow(
            {
                "game_id": result.game_id,
                "date": result.date,
                "white_model": result.white_model,
                "black_model": result.black_model,
                "result": result.result,
                "winner_model": result.winner_model or "",
                "termination": result.termination,
                "total_moves": result.total_moves,
                "time_control": result.time_control,
                "white_clock_end": round(result.white_clock_end, 2),
                "black_clock_end": round(result.black_clock_end, 2),
                "duration_sec": round(result.duration_sec, 2),
                "white_moves": result.white_moves,
                "black_moves": result.black_moves,
                "white_think_sec": round(result.white_think_sec, 2),
                "black_think_sec": round(result.black_think_sec, 2),
                "total_input_tokens": result.total_input_tokens,
                "total_output_tokens": result.total_output_tokens,
                "total_cost_usd": round(result.total_cost_usd, 6),
                "white_cost_usd": round(result.white_cost_usd, 6),
                "black_cost_usd": round(result.black_cost_usd, 6),
                "white_retries": result.white_retries,
                "black_retries": result.black_retries,
                "total_retries": result.total_retries,
                "pgn_path": result.pgn_path,
                "report_path": result.report_path,
            }
        )


def list_games() -> list[dict]:
    """Return finished games from the CSV index (newest first)."""
    if not GAMES_CSV.exists():
        return []
    with GAMES_CSV.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    rows.reverse()
    return rows


def load_report(game_id: str) -> dict | None:
    path = REPORTS_DIR / f"{game_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_pgn(game_id: str) -> str | None:
    path = PGN_DIR / f"{game_id}.pgn"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def pgn_path_for(game_id: str) -> str:
    return str(PGN_DIR / f"{game_id}.pgn")


def report_path_for(game_id: str) -> str:
    return str(REPORTS_DIR / f"{game_id}.json")
