"""Boundary tests for backend events and their output port."""

import pytest

from superhp_agent.contracts import BackendEvent
from superhp_agent.ports import emit_backend_event


class RecordingEventSink:
    def __init__(self):
        self.events: list[BackendEvent] = []

    async def emit_event(self, event: BackendEvent) -> None:
        self.events.append(event)


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
