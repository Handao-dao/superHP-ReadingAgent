"""Provider-neutral data returned by the language-model boundary.

This contract contains normalized model output only. It does not expose vendor
SDK response objects, perform retries, choose models, or make network calls.
"""

from dataclasses import dataclass, field


@dataclass
class LLMResponse:
    """Normalized response envelope consumed by application services."""

    content: str | None
    finish_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict)
    reasoning_content: str | None = None
    retry_after: float | None = None
    error_status_code: int | None = None
    error_kind: str | None = None
    error_type: str | None = None
    error_code: str | None = None
    error_retry_after_s: float | None = None
    error_should_retry: bool | None = None

    @property
    def is_error(self) -> bool:
        return self.finish_reason == "error"
