"""Pydantic schemas shared across the backend.

These describe the configuration of a game, what an agent observes on its turn,
and the records/reports we persist. Pure-chess state (board legality, SAN/UCI,
draws) lives in ``python-chess`` and is not duplicated here.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Agent + game configuration
# --------------------------------------------------------------------------- #
class AgentSpec(BaseModel):
    """How to construct one side's agent.

    ``provider`` selects the AI company / engine (see ``backend.providers``):
    "mock", "deepseek", "gpt", or "claude". ``model`` picks one of that
    provider's models (defaults to the provider's default). ``name`` is the label
    stored in reports/PGN (defaults to the model, or the provider label).
    """

    provider: Literal["mock", "deepseek", "gpt", "claude"] = "mock"
    model: Optional[str] = None
    name: Optional[str] = None

    # claude only: "fast" (no extended thinking) | "adaptive" (thinks, uses more clock)
    thinking: Literal["fast", "adaptive"] = "fast"

    # mock only. Default think is a fixed 4s so that with a typical +2s increment
    # the mock's clock still counts down (4 > 2) and its games end on time rather
    # than dragging on forever.
    illegal_prob: float = 0.0
    think_min: float = 4.0
    think_max: float = 4.0


class GameConfig(BaseModel):
    """Per-game settings, including the fully configurable time control.

    Defaults to a 3+2 blitz: 180 seconds (3 minutes) base per player, +2 seconds
    added to the mover's clock after every legal move.
    """

    base_seconds: int = Field(default=180, ge=1, description="Base time per player (s)")
    increment_seconds: int = Field(default=2, ge=0, description="Fischer increment (s)")
    white: AgentSpec = Field(default_factory=AgentSpec)
    black: AgentSpec = Field(default_factory=AgentSpec)
    event: str = "Chess Blitz AI"

    @property
    def time_control_str(self) -> str:
        """PGN-style time control, e.g. ``"60+2"``."""
        return f"{self.base_seconds}+{self.increment_seconds}"


# --------------------------------------------------------------------------- #
# Observation handed to an agent on its turn
# --------------------------------------------------------------------------- #
class Observation(BaseModel):
    """Everything an agent needs to choose a move."""

    color: Literal["white", "black"]
    fen: str
    move_history_san: list[str]
    legal_moves_uci: list[str]
    fullmove_number: int
    your_clock: float
    opponent_clock: float
    increment: int
    # moves this turn that were already rejected as illegal (set on a retry)
    rejected_moves: list[str] = []


# --------------------------------------------------------------------------- #
# Persisted records / reports
# --------------------------------------------------------------------------- #
class MoveDecision(BaseModel):
    """What an agent returns for one turn: the move plus its cost."""

    move: str
    reasoning: str = ""
    think_time: float = 0.0  # seconds (deducted from the clock)
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Optional[float] = None  # None if the model has no listed price
    retries: int = 0  # reconnects needed due to a stalled/bad connection


class MoveRecord(BaseModel):
    """One played (legal) move plus its per-move report."""

    ply: int
    fullmove_number: int
    color: Literal["white", "black"]
    mover_model: str
    san: str
    uci: str
    fen_after: str
    think_time: float
    white_clock: float
    black_clock: float
    reasoning: str = ""
    note: str = ""  # e.g. penalty applied before this move
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Optional[float] = None
    retries: int = 0  # reconnects on this move due to a stalled connection


class GameResult(BaseModel):
    """Final per-game report ('which model won and why')."""

    game_id: str
    date: str
    white_model: str
    black_model: str
    result: str  # "1-0" | "0-1" | "1/2-1/2" | "*"
    winner_model: Optional[str]
    winner_color: Optional[Literal["white", "black"]]
    termination: str  # checkmate | timeout | illegal_forfeit | stalemate | draw_*
    why: str
    total_moves: int
    time_control: str
    white_clock_end: float
    black_clock_end: float
    duration_sec: float
    # per-side move counts and total seconds spent thinking (sum of think times)
    white_moves: int = 0
    black_moves: int = 0
    white_think_sec: float = 0.0
    black_think_sec: float = 0.0
    # cost accounting
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    white_cost_usd: float = 0.0
    black_cost_usd: float = 0.0
    # reconnects due to stalled/bad connections
    white_retries: int = 0
    black_retries: int = 0
    total_retries: int = 0
    pgn_path: str
    report_path: str
