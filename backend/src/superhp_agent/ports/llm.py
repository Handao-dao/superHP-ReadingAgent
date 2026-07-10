"""Minimal language-model capability required by application services.

The port describes what Services need, not how a vendor SDK, retry policy, or
provider registry works. Infrastructure providers satisfy this Protocol
structurally.
"""

from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

from superhp_agent.contracts.llm import LLMResponse


@runtime_checkable
class LLMProvider(Protocol):
    """Capability for one retry-aware model conversation request."""

    async def chat_with_retry(
        self,
        messages: list[dict[str, Any]],
        *,
        on_retry_wait: Callable[[str], Awaitable[None]] | None = None,
    ) -> LLMResponse: ...
