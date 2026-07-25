"""Boundary tests for the language-model port."""

from superhp_agent.contracts import LLMResponse
from superhp_agent.ports import LLMProvider


class MinimalProvider:
    async def chat_with_retry(
        self,
        messages,
        *,
        tools=None,
        on_retry_wait=None,
    ):
        return LLMResponse(content="ok")


def test_minimal_provider_satisfies_application_port():
    assert isinstance(MinimalProvider(), LLMProvider)
