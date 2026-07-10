"""Runtime event adapters and compatibility exports.

The event data contract and output port now live in ``contracts.events`` and
``ports.events``. This module retains legacy imports and callback/no-op adapters;
new services should depend on the port directly.
"""

from __future__ import annotations

from superhp_agent.contracts.events import BackendEvent
from superhp_agent.ports.events import EventEmitter, EventSink, emit_backend_event

__all__ = [
    "BackendEvent",
    "CallableEventSink",
    "EventEmitter",
    "EventSink",
    "NullEventSink",
    "emit_backend_event",
]


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
