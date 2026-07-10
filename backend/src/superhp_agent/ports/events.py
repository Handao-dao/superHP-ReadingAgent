"""Output port for publishing transport-neutral backend events.

Services and application handlers depend on this capability instead of a
WebSocket, logger, or runtime implementation. This module does not decide event
recipients or perform transport serialization.
"""

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from superhp_agent.contracts.events import BackendEvent


class EventSink(Protocol):
    """Capability required by code that publishes backend events."""

    async def emit_event(self, event: BackendEvent) -> None: ...


class EventLogger(Protocol):
    """Capability required by code that records append-only behavior events."""

    def log_event(self, event_type: str, **payload: Any) -> None: ...


EventEmitter = Callable[..., Awaitable[None]]


async def emit_backend_event(
    sink: EventSink,
    event_type: str,
    *,
    request_id: str | None = None,
    **payload: Any,
) -> None:
    """Build and publish an event through the output port."""
    await sink.emit_event(BackendEvent(type=event_type, request_id=request_id, payload=payload))
