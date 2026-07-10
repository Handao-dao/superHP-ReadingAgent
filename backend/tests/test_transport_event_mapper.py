"""Transport mapping tests for reading.v1 backend event messages."""

from superhp_agent.contracts import BackendEvent
from superhp_agent.transport.event_mapper import event_to_websocket_message


def test_event_mapper_keeps_flat_websocket_shape():
    event = BackendEvent(
        type="annotation.progress",
        request_id="req-1",
        payload={"completed": 2, "total": 4},
    )

    assert event_to_websocket_message(event) == {
        "type": "annotation.progress",
        "request_id": "req-1",
        "completed": 2,
        "total": 4,
    }


def test_event_mapper_omits_missing_request_id():
    event = BackendEvent(type="ready", payload={"protocol": "reading.v1"})

    assert event_to_websocket_message(event) == {
        "type": "ready",
        "protocol": "reading.v1",
    }
