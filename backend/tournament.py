"""Round-robin tournament between all players, run strictly one game at a time.

Every pair plays ``--games`` games (colors alternate). Scoring: win = 1, draw =
0.5, loss = 0. Each game is a normal headless :class:`BlitzGame` (so it's saved
to ``data/`` like any other game). Progress is written to
``data/tournament.json`` after every game, so standings can be watched live and
the run resumes where it left off if interrupted.

    python -m backend.tournament --tc 3+2 --games 5

Only one game runs at any moment (sequential loop) — no parallel API load.
"""

from __future__ import annotations

import argparse
import itertools
import json
import logging
import time
from pathlib import Path

from .agents.factory import build_agent
from .game import BlitzGame
from .models import AgentSpec, GameConfig

logger = logging.getLogger("chess_blitz.tournament")

STATE_PATH = Path("data/tournament.json")

# The 7 players: 1 mock, 2 OpenAI, 2 Claude, 2 DeepSeek.
PLAYERS: list[tuple[str, AgentSpec]] = [
    ("mock", AgentSpec(provider="mock", name="mock")),
    ("gpt-5.5", AgentSpec(provider="gpt", model="gpt-5.5", name="gpt-5.5")),
    ("o4-mini", AgentSpec(provider="gpt", model="o4-mini", name="o4-mini")),
    ("claude-opus-4-8", AgentSpec(provider="claude", model="claude-opus-4-8", name="claude-opus-4-8")),
    ("claude-haiku-4-5", AgentSpec(provider="claude", model="claude-haiku-4-5", name="claude-haiku-4-5")),
    ("deepseek-v4-flash", AgentSpec(provider="deepseek", model="deepseek-v4-flash", name="deepseek-v4-flash")),
    ("deepseek-v4-pro", AgentSpec(provider="deepseek", model="deepseek-v4-pro", name="deepseek-v4-pro")),
]
SPECS = dict(PLAYERS)
PLAYER_IDS = [pid for pid, _ in PLAYERS]


def parse_tc(tc: str) -> tuple[int, int]:
    if "+" in tc:
        base, inc = tc.split("+", 1)
        return int(base), int(inc)
    return int(tc), 0


def schedule(games_per_pair: int) -> list[dict]:
    """Deterministic game list. Colors alternate within each pairing."""
    games = []
    for a, b in itertools.combinations(PLAYER_IDS, 2):
        for g in range(games_per_pair):
            white, black = (a, b) if g % 2 == 0 else (b, a)
            games.append({"pair": [a, b], "game_idx": g, "white": white, "black": black})
    return games


def compute_standings(results: list[dict]) -> list[dict]:
    pts = {pid: 0.0 for pid in PLAYER_IDS}
    wdl = {pid: [0, 0, 0] for pid in PLAYER_IDS}  # w, d, l
    for r in results:
        if r.get("termination") == "error":
            continue
        w, b, winner = r["white"], r["black"], r.get("winner")
        if winner is None:  # draw
            pts[w] += 0.5; pts[b] += 0.5
            wdl[w][1] += 1; wdl[b][1] += 1
        else:
            loser = b if winner == w else w
            pts[winner] += 1.0
            wdl[winner][0] += 1; wdl[loser][2] += 1
    table = [
        {"player": pid, "points": pts[pid],
         "w": wdl[pid][0], "d": wdl[pid][1], "l": wdl[pid][2],
         "games": sum(wdl[pid])}
        for pid in PLAYER_IDS
    ]
    table.sort(key=lambda x: (-x["points"], -x["w"], x["player"]))
    return table


def save_state(config: dict, results: list[dict]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(
            {"config": config, "standings": compute_standings(results), "games": results},
            indent=2,
        ),
        encoding="utf-8",
    )


def load_done() -> tuple[list[dict], set[tuple]]:
    """Return prior results and the set of *successfully completed* game keys.

    Voided (error) games are dropped so a resume re-plays them — e.g. after
    topping up API credits that ran out mid-run.
    """
    if not STATE_PATH.exists():
        return [], set()
    data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    kept = [r for r in data.get("games", []) if r.get("termination") != "error"]
    done = {(r["white"], r["black"], r["game_idx"]) for r in kept}
    return kept, done


def play_one(white_id: str, black_id: str, base: int, inc: int, max_plies: int) -> dict:
    config = GameConfig(base_seconds=base, increment_seconds=inc,
                        white=SPECS[white_id], black=SPECS[black_id])
    white = build_agent(config.white, white_id)
    black = build_agent(config.black, black_id)
    game = BlitzGame(config, white, black, realtime=False, max_plies=max_plies)
    result = game.run()
    winner = None
    if result.winner_color == "white":
        winner = white_id
    elif result.winner_color == "black":
        winner = black_id
    return {
        "game_id": result.game_id, "result": result.result,
        "winner": winner, "termination": result.termination,
        "total_moves": result.total_moves,
    }


def print_standings(results: list[dict]) -> None:
    print("\n=== STANDINGS ===")
    print(f"{'#':>2}  {'player':22s} {'pts':>5} {'W':>3} {'D':>3} {'L':>3} {'games':>5}")
    for i, row in enumerate(compute_standings(results), 1):
        print(f"{i:>2}  {row['player']:22s} {row['points']:>5.1f} "
              f"{row['w']:>3} {row['d']:>3} {row['l']:>3} {row['games']:>5}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    parser = argparse.ArgumentParser(description="Round-robin tournament (sequential).")
    parser.add_argument("--tc", default="180+2",
                        help="time control base+increment IN SECONDS (chess 3+2 = 180+2)")
    parser.add_argument("--games", type=int, default=5, help="games per pairing")
    parser.add_argument("--max-plies", type=int, default=200,
                        help="adjudicate by material if a game reaches this length")
    parser.add_argument("--game-retries", type=int, default=2,
                        help="retries if a whole game errors out (unreachable)")
    args = parser.parse_args()

    base, inc = parse_tc(args.tc)
    config = {"time_control": f"{base}+{inc}", "games_per_pair": args.games,
              "max_plies": args.max_plies, "players": PLAYER_IDS}

    all_games = schedule(args.games)
    results, done = load_done()
    total = len(all_games)
    remaining = [g for g in all_games if (g["white"], g["black"], g["game_idx"]) not in done]

    logger.info("Tournament: %d players, %s, %d games/pair = %d games total; "
                "%d already done, %d to play.",
                len(PLAYER_IDS), config["time_control"], args.games, total,
                total - len(remaining), len(remaining))

    for n, g in enumerate(remaining, 1):
        w, b, gi = g["white"], g["black"], g["game_idx"]
        logger.info("[%d/%d] %s (W) vs %s (B) — game %d of pairing",
                    n, len(remaining), w, b, gi + 1)
        rec = {**g}
        last_err = None
        for attempt in range(args.game_retries + 1):
            try:
                rec.update(play_one(w, b, base, inc, args.max_plies))
                last_err = None
                break
            except Exception as exc:  # noqa: BLE001 — keep the tournament going
                last_err = exc
                logger.warning("game %s vs %s errored (attempt %d): %s",
                               w, b, attempt + 1, exc)
                time.sleep(3)
        if last_err is not None:
            rec.update({"termination": "error", "winner": None, "result": "*"})
            logger.error("voiding game %s vs %s after retries: %s", w, b, last_err)
        else:
            logger.info("   -> %s | %s", rec["result"], rec["termination"])
        results.append(rec)
        save_state(config, results)  # live standings + resume point

    print_standings(results)
    save_state(config, results)
    print(f"\nSaved standings to {STATE_PATH}. Individual games saved under data/.")


if __name__ == "__main__":
    main()
