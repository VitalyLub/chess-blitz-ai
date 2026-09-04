"""Provider registry: the single place that lists each AI company, the models you
can pick from it, its default model, and how to reach it (env var / base URL).

Add or edit models here and they automatically show up in the runner CLI and the
frontend's new-game dropdowns (served via GET /providers). Keys are secrets and
are read from the named environment variable at call time — never stored here.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class Provider(BaseModel):
    key: str  # spec.provider value
    label: str  # human label for the UI
    engine: str  # which agent implementation: "mock" | "openai" | "anthropic"
    models: list[str]  # selectable models (first is the default)
    api_key_env: Optional[str] = None  # env var holding the API key
    base_url: Optional[str] = None  # OpenAI-compatible base URL (deepseek etc.)
    supports_thinking: bool = False  # exposes the fast/adaptive thinking toggle

    @property
    def default_model(self) -> Optional[str]:
        return self.models[0] if self.models else None


PROVIDERS: dict[str, Provider] = {
    "mock": Provider(
        key="mock",
        label="Mock (random)",
        engine="mock",
        models=[],
    ),
    "deepseek": Provider(
        key="deepseek",
        label="DeepSeek",
        engine="openai",
        # First entry is the default. These are the ids the DeepSeek API serves
        # (from GET https://api.deepseek.com/models). Edit to add/remove.
        models=["deepseek-v4-flash", "deepseek-v4-pro"],
        api_key_env="DEEPSEEK_API_KEY",
        base_url="https://api.deepseek.com",
    ),
    "gpt": Provider(
        key="gpt",
        label="OpenAI GPT",
        engine="openai",
        models=["gpt-5.5", "o4-mini"],
        api_key_env="OPENAI_API_KEY",
        base_url="https://api.openai.com/v1",
    ),
    "claude": Provider(
        key="claude",
        label="Anthropic Claude",
        engine="anthropic",
        models=[
            "claude-opus-4-8",
            "claude-haiku-4-5",
        ],
        api_key_env="ANTHROPIC_API_KEY",
        base_url=None,
        supports_thinking=True,
    ),
}


def get_provider(key: str) -> Provider:
    if key not in PROVIDERS:
        raise ValueError(f"Unknown provider: {key!r}. Known: {list(PROVIDERS)}")
    return PROVIDERS[key]
