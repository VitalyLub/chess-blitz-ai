"""Agent for Anthropic Claude via the official Anthropic SDK.

Uses the Messages API. The system prompt instructs a JSON-only reply, which we
parse tolerantly — this keeps the agent working across Claude model versions
(Sonnet 4.5, Opus/Sonnet/Haiku 4.x) that differ in structured-output / thinking
support. Two thinking modes (chosen per game):

- "fast":     no extended thinking (lowest latency — fair for a blitz clock).
- "adaptive": Claude thinks adaptively at high effort (stronger moves, more
              wall-clock time = more of its blitz clock). Silently falls back to
              a plain request on models that don't support adaptive thinking.

Wall-clock time of the call is reported as the think time deducted from the clock.
"""

from __future__ import annotations

import anthropic

from ..models import MoveDecision, Observation
from ..pricing import cost_usd
from ..prompts import move_prompt, system_prompt
from .base import Agent
from .openai_agent import parse_reply  # tolerant {move, reasoning} JSON parser


class ClaudeAgent(Agent):
    def __init__(
        self,
        name: str,
        model: str = "claude-opus-4-8",
        api_key_env: str = "ANTHROPIC_API_KEY",
        thinking: str = "fast",
    ) -> None:
        import os

        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError(
                f"Missing API key: set the {api_key_env} environment variable."
            )
        self.name = name
        self.model = model
        self.thinking = thinking
        # We own retries (reconnect-on-stall), so disable the SDK's retry loop.
        self._client = anthropic.Anthropic(api_key=api_key, max_retries=0)

    def choose_move(self, obs: Observation) -> MoveDecision:
        from ._reconnect import call_with_reconnect, logger

        retry_errors = (
            anthropic.APITimeoutError, anthropic.APIConnectionError,
            anthropic.RateLimitError, anthropic.InternalServerError,
            anthropic.OverloadedError,
        )
        base_kwargs: dict = {
            "model": self.model,
            "max_tokens": 1024,
            "system": system_prompt(obs.color),
            "messages": [{"role": "user", "content": move_prompt(obs)}],
        }
        # Try adaptive thinking first (newer models), then legacy extended
        # thinking (Sonnet 4.5), then a plain request. Only used when thinking is
        # "adaptive"; "fast" is a single plain request.
        attempts: list[dict] = []
        if self.thinking == "adaptive":
            attempts.append({
                **base_kwargs, "max_tokens": 8000,
                "thinking": {"type": "adaptive"},
                "output_config": {"effort": "high"},
            })
            attempts.append({
                **base_kwargs, "max_tokens": 8000,
                "thinking": {"type": "enabled", "budget_tokens": 2000},
            })
        attempts.append(base_kwargs)  # fast / plain

        resp = None
        think_time = 0.0
        retries = 0
        last_err: Exception | None = None
        for kw in attempts:
            try:
                resp, think_time, retries = call_with_reconnect(
                    lambda t, kw=kw: self._client.with_options(
                        timeout=t
                    ).messages.create(**kw),
                    retry_errors,
                    on_retry=lambda n, e: logger.warning(
                        "%s: no response in time, reconnect attempt %d "
                        "(bad connection): %s", self.model, n, type(e).__name__,
                    ),
                )
                break
            except anthropic.BadRequestError as e:
                last_err = e  # model rejects this mode → try the next one
            except retry_errors as e:
                last_err = e  # reconnects exhausted for this mode → try the next
        if resp is None:
            raise last_err  # type: ignore[misc]

        text = next((b.text for b in resp.content if b.type == "text"), "")
        move, reasoning = parse_reply(text)

        in_tok = getattr(resp.usage, "input_tokens", 0) or 0
        out_tok = getattr(resp.usage, "output_tokens", 0) or 0
        return MoveDecision(
            move=move,
            reasoning=reasoning,
            think_time=think_time,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=cost_usd(self.model, in_tok, out_tok),
            retries=retries,
        )
