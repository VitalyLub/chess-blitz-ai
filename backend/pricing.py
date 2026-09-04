"""Per-model token pricing (USD per 1,000,000 tokens).

EDIT THESE to match current provider pricing — they change over time and some
are best-effort placeholders. Unknown models return ``None`` cost (the UI then
shows tokens/time but no dollar figure).
"""

from __future__ import annotations

from typing import Optional

# model id -> {"in": input $/1M, "out": output $/1M}
PRICES: dict[str, dict[str, float]] = {
    # Anthropic Claude (from Anthropic pricing)
    "claude-opus-4-8": {"in": 5.00, "out": 25.00},
    "claude-haiku-4-5": {"in": 1.00, "out": 5.00},
    # DeepSeek (verify at deepseek.com — placeholders)
    "deepseek-v4-flash": {"in": 0.28, "out": 0.42},
    "deepseek-v4-pro": {"in": 0.55, "out": 2.19},
    # OpenAI (verify at openai.com — placeholders)
    "gpt-5.5": {"in": 1.25, "out": 10.00},
    "o4-mini": {"in": 1.10, "out": 4.40},
}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> Optional[float]:
    """Dollar cost for one call, or ``None`` if the model has no listed price."""
    p = PRICES.get(model)
    if not p:
        return None
    return (input_tokens * p["in"] + output_tokens * p["out"]) / 1_000_000
