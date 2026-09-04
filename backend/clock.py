"""A simple chess clock with a Fischer increment.

The base time and increment both come from the game's :class:`GameConfig`, so a
game can run at any time control (default 60+2).
"""

from __future__ import annotations


class Clock:
    def __init__(self, base_seconds: float, increment_seconds: float) -> None:
        self.base_seconds = float(base_seconds)
        self.increment_seconds = float(increment_seconds)
        self.remaining = float(base_seconds)

    def consume(self, elapsed: float) -> bool:
        """Subtract think time. Returns ``True`` if the flag fell (time out)."""
        self.remaining -= max(0.0, elapsed)
        if self.remaining <= 0.0:
            self.remaining = 0.0
            return True
        return False

    def add_increment(self) -> None:
        """Apply the Fischer increment after a legal move."""
        self.remaining += self.increment_seconds

    def add_penalty(self, seconds: float) -> None:
        """Add compensation time (e.g. opponent's illegal-move penalty)."""
        self.remaining += seconds

    @property
    def flagged(self) -> bool:
        return self.remaining <= 0.0


def format_clock(seconds: float) -> str:
    """Format seconds as ``H:MM:SS`` for PGN ``%clk`` annotations."""
    seconds = max(0, int(round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}"
