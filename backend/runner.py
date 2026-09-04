"""Headless runner: play games between two agents from the command line.

Examples:
    python -m backend.runner --white mock --black mock --games 3
    python -m backend.runner --tc 180+5 --games 1
    python -m backend.runner --games 5 --illegal-prob 0.1   # exercise penalties
"""

from __future__ import annotations

import argparse

from .agents.factory import build_agent
from .game import BlitzGame
from .models import AgentSpec, GameConfig


def parse_tc(tc: str) -> tuple[int, int]:
    """Parse a ``base+increment`` time control (e.g. ``"60+2"``)."""
    if "+" in tc:
        base, inc = tc.split("+", 1)
        return int(base), int(inc)
    return int(tc), 0


def build_config(args: argparse.Namespace) -> GameConfig:
    base, inc = parse_tc(args.tc)
    white = AgentSpec(
        provider=args.white,
        name=args.white_name,
        model=args.white_model,
        thinking=args.white_thinking,
        illegal_prob=args.illegal_prob,
    )
    black = AgentSpec(
        provider=args.black,
        name=args.black_name,
        model=args.black_model,
        thinking=args.black_thinking,
        illegal_prob=args.illegal_prob,
    )
    return GameConfig(
        base_seconds=base, increment_seconds=inc, white=white, black=black
    )


def main() -> None:
    providers = ["mock", "deepseek", "gpt", "claude"]
    parser = argparse.ArgumentParser(description="Run blitz games between agents headlessly.")
    parser.add_argument("--white", default="mock", choices=providers)
    parser.add_argument("--black", default="mock", choices=providers)
    parser.add_argument("--white-name", default=None)
    parser.add_argument("--black-name", default=None)
    parser.add_argument("--white-model", default=None, help="model id (defaults to provider default)")
    parser.add_argument("--black-model", default=None, help="model id (defaults to provider default)")
    parser.add_argument("--white-thinking", default="fast", choices=["fast", "adaptive"], help="claude only")
    parser.add_argument("--black-thinking", default="fast", choices=["fast", "adaptive"], help="claude only")
    parser.add_argument("--tc", default="180+2", help="time control base+increment")
    parser.add_argument("--games", type=int, default=1)
    parser.add_argument("--illegal-prob", type=float, default=0.0)
    args = parser.parse_args()

    for i in range(args.games):
        config = build_config(args)
        white = build_agent(config.white, "white")
        black = build_agent(config.black, "black")
        game = BlitzGame(config, white, black, realtime=False)
        result = game.run()
        print(
            f"[{i + 1}/{args.games}] {result.game_id} "
            f"({result.time_control})  {result.result}  "
            f"{result.termination}  |  {result.why}"
        )


if __name__ == "__main__":
    main()
