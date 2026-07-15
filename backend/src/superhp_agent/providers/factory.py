"""Create LLM providers from application settings."""

from __future__ import annotations

from superhp_agent.config import Settings
from superhp_agent.ports.llm import LLMProvider
from superhp_agent.providers.base import GenerationSettings
from superhp_agent.providers.openai_compat import OpenAICompatProvider
from superhp_agent.providers.registry import find_by_name, match_by_model


def make_provider(settings: Settings) -> LLMProvider:
    """Create the configured provider from settings and registry metadata."""
    spec = find_by_name(settings.llm_provider) or match_by_model(settings.llm_model_id)
    if spec is None:
        spec = find_by_name("custom")
    if spec is None:
        raise ValueError("No provider spec configured")
    if spec.requires_api_key and not settings.llm_api_key:
        raise ValueError(f"No API key configured for provider '{spec.name}'")

    provider = OpenAICompatProvider(
        api_key=settings.llm_api_key or None,
        api_base=settings.llm_base_url or spec.default_api_base or None,
        default_model=settings.llm_model_id,
        timeout=settings.llm_timeout,
        spec=spec,
    )
    provider.generation = GenerationSettings(
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )
    return provider
