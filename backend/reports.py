"""Compose the per-game result / 'why' summary from a finished game."""

from __future__ import annotations

from typing import Optional

# termination -> human phrase builder
_DRAW_PHRASES = {
    "stalemate": "stalemate",
    "draw_insufficient_material": "insufficient material",
    "draw_seventyfive_moves": "the seventy-five-move rule",
    "draw_fivefold_repetition": "fivefold repetition",
    "draw_agreed": "agreement",
}


def result_string(winner_color: Optional[str]) -> str:
    if winner_color == "white":
        return "1-0"
    if winner_color == "black":
        return "0-1"
    return "1/2-1/2"


def build_why(
    termination: str,
    winner_color: Optional[str],
    winner_model: Optional[str],
    loser_model: Optional[str],
    total_moves: int,
) -> str:
    """Build the natural-language 'which model won and why' sentence."""
    if termination == "checkmate":
        return (
            f"{_cap(winner_color)} ({winner_model}) won by checkmate "
            f"after {total_moves} moves."
        )
    if termination == "timeout":
        return (
            f"{_cap(winner_color)} ({winner_model}) won on time; "
            f"{loser_model} flagged after {total_moves} moves."
        )
    if termination == "illegal_forfeit":
        return (
            f"{_cap(winner_color)} ({winner_model}) won: {loser_model} forfeited "
            f"after a second illegal move."
        )
    phrase = _DRAW_PHRASES.get(termination, "a draw")
    return f"Draw by {phrase} after {total_moves} moves."


def _cap(color: Optional[str]) -> str:
    return color.capitalize() if color else "Nobody"
