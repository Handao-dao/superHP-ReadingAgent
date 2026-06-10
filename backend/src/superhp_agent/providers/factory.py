"""Create LLM providers from application settings."""

from __future__ import annotations

from dataclasses import dataclass

from superhp_agent.config import Settings
from superhp_agent.providers.base import GenerationSettings, LLMProvider
from superhp_agent.providers.openai_compat import OpenAICompatProvider
from superhp_agent.providers.registry import find_by_name, match_by_model


@dataclass(frozen=True)
class ProviderSnapshot:
    """Provider plus config signature for future hot-reload comparisons."""
    provider: LLMProvider
    model: str
    provider_name: str
    signature: tuple[object, ...]


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


def provider_signature(settings: Settings) -> tuple[object, ...]:
    """Return non-secret settings that identify the active provider config."""
    return (
        settings.llm_provider,
        settings.llm_model_id,
        settings.llm_base_url,
        bool(settings.llm_api_key),
        settings.llm_timeout,
        settings.llm_temperature,
        settings.llm_max_tokens,
    )


def build_provider_snapshot(settings: Settings) -> ProviderSnapshot:
    spec = find_by_name(settings.llm_provider) or match_by_model(settings.llm_model_id)
    provider_name = spec.name if spec else "custom"
    return ProviderSnapshot(
        provider=make_provider(settings),
        model=settings.llm_model_id,
        provider_name=provider_name,
        signature=provider_signature(settings),
    )