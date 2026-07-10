"""Boundary and compatibility tests for backend events and their output port."""

import pytest

from superhp_agent.contracts import BackendEvent
from superhp_agent.ports import EventSink, emit_backend_event
from superhp_agent.runtime.events import BackendEvent as LegacyBackendEvent
from superhp_agent.runtime.events import EventSink as LegacyEventSink


class RecordingEventSink:
    def __init__(self):
        self.events: list[BackendEvent] = []

    async def emit_event(self, event: BackendEvent) -> None:
        self.events.append(event)


def test_runtime_events_keeps_legacy_contract_and_port_imports():
    assert LegacyBackendEvent is BackendEvent
    assert LegacyEventSink is EventSink


@pytest.mark.asyncio
async def test_event_port_builds_transport_neutral_event():
    sink = RecordingEventSink()

    await emit_backend_event(sink, "annotation.progress", request_id="req-1", completed=2, total=4)

    assert sink.events == [
        BackendEvent(
            type="annotation.progress",
            request_id="req-1",
            payload={"completed": 2, "total": 4},
        )
    ]
