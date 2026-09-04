"""Reconnect wrapper for flaky agent API calls.

If an agent doesn't respond within ``timeout`` seconds, abort that attempt and
send a fresh request (up to ``max_retries`` times). Crucially, only the
**successful** attempt's wall time is returned as the think time — the stalled
time is refunded, so a connection hiccup can't drain a player's clock. Each
reconnect is logged as a "bad connection" warning.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

logger = logging.getLogger("chess_blitz.reconnect")

RESPONSE_TIMEOUT_SEC = 30.0  # wait this long for a response before retrying
MAX_RECONNECTS = 3           # extra attempts after the first (initial + 3 = 4 tries)


def call_with_reconnect(
    make_call: Callable[[float], object],
    retry_errors: tuple[type[BaseException], ...],
    timeout: float = RESPONSE_TIMEOUT_SEC,
    max_retries: int = MAX_RECONNECTS,
    on_retry: Callable[[int, BaseException], None] | None = None,
):
    """Run ``make_call(timeout)`` with reconnect-on-stall.

    Returns ``(response, successful_elapsed_sec, retries)``. Raises the last error
    if every attempt (initial + ``max_retries``) fails.
    """
    attempt = 0
    last_err: BaseException | None = None
    while True:
        start = time.monotonic()
        try:
            response = make_call(timeout)
            return response, time.monotonic() - start, attempt
        except retry_errors as exc:
            last_err = exc
            attempt += 1
            if on_retry is not None:
                on_retry(attempt, exc)
            else:
                logger.warning(
                    "no response within %.0fs, reconnect attempt %d (bad connection): %s",
                    timeout, attempt, type(exc).__name__,
                )
            if attempt > max_retries:
                raise last_err
