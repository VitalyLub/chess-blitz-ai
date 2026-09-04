"""A mock agent that plays random legal moves.

Used to exercise the whole pipeline (clocks, penalties, storage, live view,
replay) without any real LLM. ``illegal_prob`` lets it occasionally emit an
illegal move so the penalty/forfeit path can be tested.
"""

from __future__ import annotations

import random

import chess

from ..models import MoveDecision, Observation
from .base import Agent

_REASONS = [
    "Playing quickly to save time.",
]


class MockAgent(Agent):
    def __init__(
        self,
        name: str = "mock",
        illegal_prob: float = 0.0,
        think_min: float = 4.0,
        think_max: float = 4.0,
        seed: int | None = None,
    ) -> None:
        self.name = name
        self.illegal_prob = illegal_prob
        self.think_min = think_min
        self.think_max = think_max
        self._rng = random.Random(seed)

    def choose_move(self, obs: Observation) -> MoveDecision:
        think_time = self._rng.uniform(self.think_min, self.think_max)

        if self._rng.random() < self.illegal_prob:
            # Deliberately return a move that is (almost certainly) not legal.
            return MoveDecision(
                move="a1a1",
                reasoning="Fumbled under time pressure.",
                think_time=think_time,
            )

        board = chess.Board(obs.fen)
        move = self._rng.choice(list(board.legal_moves))
        reasoning = self._rng.choice(_REASONS)
        # Mock has no API cost (tokens/cost stay 0/None).
        return MoveDecision(move=move.uci(), reasoning=reasoning, think_time=think_time)
