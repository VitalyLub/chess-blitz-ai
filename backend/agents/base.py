"""Agent interface: both mock and GPT-style agents implement this."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import MoveDecision, Observation


class Agent(ABC):
    """Chooses a move given an :class:`Observation`.

    ``choose_move`` returns a :class:`MoveDecision`: the (possibly illegal — the
    game validates it) UCI move, a short "why", the think time to deduct from the
    clock, and the move's cost (tokens + dollars) for real AI agents.
    """

    name: str = "agent"

    @abstractmethod
    def choose_move(self, obs: Observation) -> MoveDecision:
        raise NotImplementedError
