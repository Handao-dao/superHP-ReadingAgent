"""Provider metadata registry.

Only the first SuperHP providers live here. More can be added without changing
runtime services that depend on LLMProvider.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    keywords: tuple[str, ...]
    display_name: str
    default_api_base: str = ""
    backend: str = "openai_compat"
    thinking_style: str = ""
    requires_api_key: bool = True


PROVIDERS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        name="deepseek",
        keywords=("deepseek",),
        display_name="DeepSeek",
        default_api_base="https://api.deepseek.com",
        thinking_style="thinking_type",
    ),
    ProviderSpec(
        name="openai",
        keywords=("openai", "gpt"),
        display_name="OpenAI",
    ),
    ProviderSpec(
        name="custom",
        keywords=(),
        display_name="Custom OpenAI-compatible",
        requires_api_key=False,
    ),
)


def find_by_name(name: str | None) -> ProviderSpec | None:
    if not name:
        return None
    normalized = name.strip().lower().replace("-", "_")
    for spec in PROVIDERS:
        if spec.name == normalized:
            return spec
    return None


def match_by_model(model: str | None) -> ProviderSpec | None:
    lowered = (model or "").lower()
    for spec in PROVIDERS:
        if spec.keywords and any(keyword in lowered for keyword in spec.keywords):
            return spec
    return None