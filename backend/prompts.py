"""Prompt templates for GPT-style agents.

Kept short and explicit so a model can respond quickly under blitz time pressure.
The model is told the situation (FEN + history), both clocks, the legal moves, and
the strict output format.
"""

from __future__ import annotations

from .clock import format_clock
from .models import Observation

SYSTEM_PROMPT = """You are a chess engine playing a BLITZ game as {color}.

Rules:
- Reply with exactly one legal move.
- Time is limited. Your clock and your opponent's clock are shown each turn; if \
your clock reaches zero you lose on time.
- Illegal moves are penalised: on your first illegal move your opponent gains 60 \
seconds and you are asked to try again; a second illegal move loses the game.

Respond ONLY with a compact JSON object, no prose:
{{"move": "<UCI, e.g. e2e4 or e7e8q>", "reasoning": "<one short sentence>"}}
"""


def system_prompt(color: str) -> str:
    return SYSTEM_PROMPT.format(color=color)


def move_prompt(obs: Observation) -> str:
    history = " ".join(
        f"{i // 2 + 1}.{'' if i % 2 == 0 else '..'}{san}"
        for i, san in enumerate(obs.move_history_san)
    ) or "(no moves yet)"

    lines = [
        f"You are {obs.color}. Move number: {obs.fullmove_number}.",
        f"FEN: {obs.fen}",
        f"Moves so far: {history}",
        f"Your clock: {format_clock(obs.your_clock)}  |  "
        f"Opponent clock: {format_clock(obs.opponent_clock)}  |  "
        f"Increment: +{obs.increment}s",
        f"Legal moves (UCI): {', '.join(obs.legal_moves_uci)}",
    ]
    if obs.rejected_moves:
        rejected = ", ".join(obs.rejected_moves)
        lines.append(
            f"!!! ILLEGAL MOVE — your previous answer(s) [{rejected}] are NOT legal "
            f"and were rejected. Do NOT return them again. You have ONE attempt left: "
            f"a second illegal move loses the game immediately. Choose a DIFFERENT move, "
            f"copied EXACTLY from the 'Legal moves (UCI)' list above."
        )
    lines.append('Reply with JSON: {"move": "...", "reasoning": "..."}')
    return "\n".join(lines)
