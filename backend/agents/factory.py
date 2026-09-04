"""Build an :class:`Agent` from an :class:`AgentSpec`, using the provider registry."""

from __future__ import annotations

from ..models import AgentSpec
from ..providers import get_provider
from .base import Agent
from .mock import MockAgent


def build_agent(spec: AgentSpec, default_name: str) -> Agent:
    provider = get_provider(spec.provider)
    model = spec.model or provider.default_model
    name = spec.name or model or provider.label or default_name

    if provider.engine == "mock":
        return MockAgent(
            name=spec.name or default_name,
            illegal_prob=spec.illegal_prob,
            think_min=spec.think_min,
            think_max=spec.think_max,
        )

    if provider.engine == "openai":
        from .openai_agent import OpenAIAgent  # lazy: avoids requiring openai for mock

        return OpenAIAgent(
            name=name,
            model=model,
            api_key_env=provider.api_key_env,
            base_url=provider.base_url,
        )

    if provider.engine == "anthropic":
        from .claude_agent import ClaudeAgent  # lazy: avoids requiring anthropic for mock

        return ClaudeAgent(
            name=name,
            model=model,
            api_key_env=provider.api_key_env,
            thinking=spec.thinking,
        )

    raise ValueError(f"Unknown engine: {provider.engine}")
