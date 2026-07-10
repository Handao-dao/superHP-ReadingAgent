"""Boundary and compatibility tests for the language-model port."""

from superhp_agent.contracts import LLMResponse
from superhp_agent.ports import LLMProvider
from superhp_agent.providers.base import LLMProvider as LegacyLLMProvider
from superhp_agent.providers.base import LLMResponse as LegacyLLMResponse


class MinimalProvider:
    async def chat_with_retry(self, messages, *, on_retry_wait=None):
        return LLMResponse(content="ok")


def test_provider_response_keeps_legacy_import():
    assert LegacyLLMResponse is LLMResponse


def test_minimal_provider_satisfies_application_port():
    assert isinstance(MinimalProvider(), LLMProvider)


def test_legacy_provider_name_remains_subclassable():
    assert hasattr(LegacyLLMProvider, "chat_with_retry")
