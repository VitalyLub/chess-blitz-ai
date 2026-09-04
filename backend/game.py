"""The blitz game engine.

Runs a full game between two agents: manages the board (via python-chess), the
clocks, the illegal-move penalty rule, terminal detection, per-move records, and
the final report. Emits events through an optional callback so a live view can
follow along; persists PGN/CSV/JSON at the end.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

import chess

from . import storage
from .agents.base import Agent
from .clock import Clock
from .models import GameConfig, GameResult, MoveRecord, Observation
from .reports import build_why, result_string

logger = logging.getLogger("chess_blitz.game")

EventCallback = Callable[[dict], None]

ILLEGAL_PENALTY_SECONDS = 60.0
MAX_ILLEGAL_STRIKES = 2

# python-chess Termination -> our termination string
_TERMINATION_MAP = {
    chess.Termination.CHECKMATE: "checkmate",
    chess.Termination.STALEMATE: "stalemate",
    chess.Termination.INSUFFICIENT_MATERIAL: "draw_insufficient_material",
    chess.Termination.SEVENTYFIVE_MOVES: "draw_seventyfive_moves",
    chess.Termination.FIVEFOLD_REPETITION: "draw_fivefold_repetition",
}


def _other(color: str) -> str:
    return "black" if color == "white" else "white"


class BlitzGame:
    def __init__(
        self,
        config: GameConfig,
        white: Agent,
        black: Agent,
        game_id: Optional[str] = None,
        on_event: Optional[EventCallback] = None,
        realtime: bool = False,
    ) -> None:
        self.config = config
        self.game_id = game_id or uuid.uuid4().hex[:12]
        self.on_event = on_event
        self.realtime = realtime

        self.board = chess.Board()
        self.agents: dict[str, Agent] = {"white": white, "black": black}
        self.clocks: dict[str, Clock] = {
            "white": Clock(config.base_seconds, config.increment_seconds),
            "black": Clock(config.base_seconds, config.increment_seconds),
        }
        self.strikes: dict[str, int] = {"white": 0, "black": 0}
        self.moves: list[MoveRecord] = []
        self.history_san: list[str] = []
        self.total_think = 0.0

    # -- event emission ---------------------------------------------------- #
    def _emit(self, event: dict) -> None:
        if self.on_event:
            self.on_event(event)

    def _clocks_snapshot(self) -> dict:
        return {
            "white": round(self.clocks["white"].remaining, 2),
            "black": round(self.clocks["black"].remaining, 2),
        }

    def _observation(self, color: str, rejected_moves: list[str]) -> Observation:
        return Observation(
            color=color,
            fen=self.board.fen(),
            move_history_san=list(self.history_san),
            legal_moves_uci=[m.uci() for m in self.board.legal_moves],
            fullmove_number=self.board.fullmove_number,
            your_clock=self.clocks[color].remaining,
            opponent_clock=self.clocks[_other(color)].remaining,
            increment=self.config.increment_seconds,
            rejected_moves=list(rejected_moves),
        )

    # -- main loop --------------------------------------------------------- #
    def run(self) -> GameResult:
        self._emit(
            {
                "type": "start",
                "game_id": self.game_id,
                "white_model": self.agents["white"].name,
                "black_model": self.agents["black"].name,
                "time_control": self.config.time_control_str,
                "fen": self.board.fen(),
                "clocks": self._clocks_snapshot(),
            }
        )

        termination: Optional[str] = None
        winner_color: Optional[str] = None

        while termination is None:
            color = "white" if self.board.turn else "black"
            outcome = self._play_turn(color)
            if outcome is not None:
                termination, winner_color = outcome
                break

            board_outcome = self.board.outcome()
            if board_outcome is not None:
                termination = _TERMINATION_MAP.get(
                    board_outcome.termination, "draw_other"
                )
                winner_color = (
                    None
                    if board_outcome.winner is None
                    else ("white" if board_outcome.winner else "black")
                )

        result = self._finalize(termination, winner_color)
        storage.save_game(self.config, result, self.moves)
        self._emit({"type": "end", "result": result.model_dump()})
        return result

    def _play_turn(self, color: str) -> Optional[tuple[str, Optional[str]]]:
        """Play one side's turn (with retry on a first illegal move).

        Returns ``(termination, winner_color)`` if the game ended this turn,
        else ``None``.
        """
        agent = self.agents[color]
        rejected: list[str] = []
        pending_note = ""

        while True:
            obs = self._observation(color, rejected)
            call_start = time.monotonic()
            decision = agent.choose_move(obs)
            call_elapsed = time.monotonic() - call_start
            move_uci = decision.move
            reasoning = decision.reasoning
            think_time = decision.think_time

            # In live mode, pace the turn so its total wall-clock ≈ think_time.
            # Real agents already blocked for ~think_time (API latency), so sleep
            # ~0; the mock returns instantly with a simulated think_time, so sleep
            # the whole amount. This keeps the browser's real-time clock in sync
            # with the time actually deducted (no snap-back each move).
            if self.realtime:
                time.sleep(max(0.0, min(think_time, 30.0) - call_elapsed))

            self.total_think += think_time
            flagged = self.clocks[color].consume(think_time)
            if flagged:
                return ("timeout", _other(color))

            if decision.retries:
                logger.warning(
                    "%s (%s) reconnected %d time(s) on a move (bad connection)",
                    agent.name, color, decision.retries,
                )

            move = self._resolve_move(move_uci)
            if move is None or move not in self.board.legal_moves:
                self.strikes[color] += 1
                opp = _other(color)
                self.clocks[opp].add_penalty(ILLEGAL_PENALTY_SECONDS)
                note = (
                    f"illegal move '{move_uci}' (strike {self.strikes[color]}"
                    f"/{MAX_ILLEGAL_STRIKES}); {opp} +{int(ILLEGAL_PENALTY_SECONDS)}s"
                )
                self._emit(
                    {
                        "type": "penalty",
                        "color": color,
                        "attempt": move_uci,
                        "strike": self.strikes[color],
                        "note": note,
                        "clocks": self._clocks_snapshot(),
                    }
                )
                if self.strikes[color] >= MAX_ILLEGAL_STRIKES:
                    return ("illegal_forfeit", opp)
                rejected.append(move_uci)
                pending_note = note
                continue

            # Legal move: apply it.
            san = self.board.san(move)
            self.board.push(move)
            self.clocks[color].add_increment()
            self.history_san.append(san)

            note = pending_note
            if decision.retries:
                recon = f"reconnected ×{decision.retries} (bad connection)"
                note = f"{note}; {recon}" if note else recon

            record = MoveRecord(
                ply=len(self.moves) + 1,
                fullmove_number=(len(self.moves) // 2) + 1,
                color=color,
                mover_model=agent.name,
                san=san,
                uci=move.uci(),
                fen_after=self.board.fen(),
                think_time=round(think_time, 3),
                white_clock=round(self.clocks["white"].remaining, 2),
                black_clock=round(self.clocks["black"].remaining, 2),
                reasoning=reasoning,
                note=note,
                input_tokens=decision.input_tokens,
                output_tokens=decision.output_tokens,
                cost_usd=decision.cost_usd,
                retries=decision.retries,
            )
            self.moves.append(record)
            self._emit(
                {
                    "type": "move",
                    "move": record.model_dump(),
                    "fen": self.board.fen(),
                    "clocks": self._clocks_snapshot(),
                    "turn": "white" if self.board.turn else "black",
                }
            )
            return None

    def _resolve_move(self, text: str) -> Optional[chess.Move]:
        """Interpret an agent's move string against the current position.

        Accepts UCI (e.g. ``d7d5``, ``e7e8q``) and, as a fallback, SAN
        (e.g. ``d5``, ``Nd5``, ``O-O``). Both are validated against the live
        board, which knows the side to move and every piece — so the result is
        always a legal move for the mover, or ``None`` when the string is
        unparseable, illegal, or ambiguous (which then counts as an illegal
        move). ``InvalidMoveError`` / ``IllegalMoveError`` / ``AmbiguousMoveError``
        all subclass ``ValueError``.
        """
        text = (text or "").strip()
        if not text:
            return None
        for parse in (self.board.parse_uci, self.board.parse_san):
            try:
                return parse(text)
            except ValueError:
                continue
        return None

    # -- result ------------------------------------------------------------ #
    def _finalize(
        self, termination: str, winner_color: Optional[str]
    ) -> GameResult:
        white_model = self.agents["white"].name
        black_model = self.agents["black"].name
        winner_model = (
            None
            if winner_color is None
            else (white_model if winner_color == "white" else black_model)
        )
        loser_model = (
            None
            if winner_color is None
            else (black_model if winner_color == "white" else white_model)
        )
        why = build_why(
            termination, winner_color, winner_model, loser_model, len(self.moves)
        )
        white_moves = sum(1 for m in self.moves if m.color == "white")
        black_moves = sum(1 for m in self.moves if m.color == "black")
        white_think = sum(m.think_time for m in self.moves if m.color == "white")
        black_think = sum(m.think_time for m in self.moves if m.color == "black")
        total_in = sum(m.input_tokens for m in self.moves)
        total_out = sum(m.output_tokens for m in self.moves)
        total_cost = sum(m.cost_usd or 0.0 for m in self.moves)
        white_cost = sum(m.cost_usd or 0.0 for m in self.moves if m.color == "white")
        black_cost = sum(m.cost_usd or 0.0 for m in self.moves if m.color == "black")
        white_retries = sum(m.retries for m in self.moves if m.color == "white")
        black_retries = sum(m.retries for m in self.moves if m.color == "black")
        return GameResult(
            game_id=self.game_id,
            date=datetime.now(timezone.utc).isoformat(),
            white_model=white_model,
            black_model=black_model,
            result=result_string(winner_color),
            winner_model=winner_model,
            winner_color=winner_color,
            termination=termination,
            why=why,
            total_moves=len(self.moves),
            time_control=self.config.time_control_str,
            white_clock_end=self.clocks["white"].remaining,
            black_clock_end=self.clocks["black"].remaining,
            duration_sec=self.total_think,
            white_moves=white_moves,
            black_moves=black_moves,
            white_think_sec=round(white_think, 2),
            black_think_sec=round(black_think, 2),
            total_input_tokens=total_in,
            total_output_tokens=total_out,
            total_cost_usd=round(total_cost, 6),
            white_cost_usd=round(white_cost, 6),
            black_cost_usd=round(black_cost, 6),
            white_retries=white_retries,
            black_retries=black_retries,
            total_retries=white_retries + black_retries,
            pgn_path=storage.pgn_path_for(self.game_id),
            report_path=storage.report_path_for(self.game_id),
        )
