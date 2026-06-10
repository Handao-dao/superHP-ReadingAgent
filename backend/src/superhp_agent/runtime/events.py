"""Backend event hook primitives.

Runtime services should report observable behavior through EventSink instead of
knowing whether the current caller is a WebSocket, test, CLI, or future HTTP
stream. This keeps progress reporting available without coupling business logic
to a transport implementation.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class BackendEvent:
    """Transport-neutral backend event emitted during guided actions."""

    type: str
    request_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def as_message(self) -> dict[str, Any]:
        """Convert to the flat JSON shape currently used by the frontend."""
        message = {"type": self.type, **self.payload}
        if self.request_id is not None:
            message["request_id"] = self.request_id
        return message


class EventSink(Protocol):
    """Hook interface for observing backend behavior."""

    async def emit_event(self, event: BackendEvent) -> None: ...


EventEmitter = Callable[..., Awaitable[None]]


class CallableEventSink:
    """Adapt the legacy ``emit(event_type, **payload)`` shape to EventSink."""

    def __init__(self, emit: EventEmitter):
        self.emit = emit

    async def emit_event(self, event: BackendEvent) -> None:
        await self.emit(event.type, request_id=event.request_id, **event.payload)


class NullEventSink:
    """No-op sink for tests or non-interactive callers."""

    async def emit_event(self, event: BackendEvent) -> None:
        return None


async def emit_backend_event(
    sink: EventSink,
    event_type: str,
    *,
    request_id: str | None = None,
    **payload: Any,
) -> None:
    """Convenience helper for callers that do not need to build BackendEvent."""
    await sink.emit_event(BackendEvent(type=event_type, request_id=request_id, payload=payload))