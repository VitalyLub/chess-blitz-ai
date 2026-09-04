"""Entry point pointing at the two ways to run Chess Blitz AI.

- Headless mock games:  python -m backend.runner --games 3
- Web server (live + replay):  uvicorn backend.app:app --reload

Running this file directly plays a single default (60+2) mock game.
"""

from backend.game import BlitzGame
from backend.agents.factory import build_agent
from backend.models import GameConfig


def main() -> None:
    config = GameConfig()
    white = build_agent(config.white, "mock-white")
    black = build_agent(config.black, "mock-black")
    result = BlitzGame(config, white, black).run()
    print(f"{result.result}  {result.termination}  |  {result.why}")
    print(f"PGN:    {result.pgn_path}")
    print(f"Report: {result.report_path}")


if __name__ == "__main__":
    main()
