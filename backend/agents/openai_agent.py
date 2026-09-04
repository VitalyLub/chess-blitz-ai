"""Agent for any OpenAI-compatible chat-completions endpoint.

Serves both OpenAI (GPT) and DeepSeek — DeepSeek exposes the same API, only the
``base_url`` differs. The API key is read from the provider's configured
environment variable. Wall-clock time of the call is reported as the think time
deducted from the player's clock.
"""

from __future__ import annotations

import json
import os
import re

from ..models import MoveDecision, Observation
from ..pricing import cost_usd
from ..prompts import move_prompt, system_prompt
from .base import Agent


class OpenAIAgent(Agent):
    def __init__(
        self,
        name: str,
        model: str,
        api_key_env: str,
        base_url: str | None = None,
    ) -> None:
        from openai import OpenAI  # lazy: mock games need no openai install/key

        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError(
                f"Missing API key: set the {api_key_env} environment variable."
            )
        self.name = name
        self.model = model
        # We own retries (reconnect-on-stall), so disable the SDK's retry loop.
        self._client = OpenAI(api_key=api_key, base_url=base_url, max_retries=0)

    def choose_move(self, obs: Observation) -> MoveDecision:
        from openai import (
            APIConnectionError, APITimeoutError, InternalServerError, RateLimitError,
        )
        from ._reconnect import call_with_reconnect, logger

        messages = [
            {"role": "system", "content": system_prompt(obs.color)},
            {"role": "user", "content": move_prompt(obs)},
        ]
        retry_errors = (
            APITimeoutError, APIConnectionError, RateLimitError, InternalServerError,
        )
        resp, think_time, retries = call_with_reconnect(
            lambda t: self._client.with_options(timeout=t).chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
            ),
            retry_errors,
            on_retry=lambda n, e: logger.warning(
                "%s: no response in time, reconnect attempt %d (bad connection): %s",
                self.model, n, type(e).__name__,
            ),
        )
        content = (resp.choices[0].message.content or "").strip()
        move, reasoning = parse_reply(content)

        usage = resp.usage
        in_tok = getattr(usage, "prompt_tokens", 0) or 0
        out_tok = getattr(usage, "completion_tokens", 0) or 0
        return MoveDecision(
            move=move,
            reasoning=reasoning,
            think_time=think_time,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=cost_usd(self.model, in_tok, out_tok),
            retries=retries,
        )


def parse_reply(content: str) -> tuple[str, str]:
    """Tolerant parse of a model reply into (move_uci, reasoning)."""
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            move = str(data.get("move", "")).strip()
            reasoning = str(data.get("reasoning", "")).strip()
            if move:
                return move, reasoning or "(no reasoning given)"
        except json.JSONDecodeError:
            pass
    uci = re.search(r"\b([a-h][1-8][a-h][1-8][qrbn]?)\b", content)
    if uci:
        return uci.group(1), content[:120]
    return content.strip()[:10], content[:120]
