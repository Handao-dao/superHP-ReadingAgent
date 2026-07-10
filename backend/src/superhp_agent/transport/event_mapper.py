"""Map application events into the reading.v1 WebSocket JSON shape.

This adapter owns the current flat message representation. It does not publish
events, execute actions, or change the transport-neutral BackendEvent contract.
"""

from typing import Any

from superhp_agent.contracts import BackendEvent


def event_to_websocket_message(event: BackendEvent) -> dict[str, Any]:
    """Convert one application event to the frontend's flat JSON message."""
    message = {"type": event.type, **event.payload}
    if event.request_id is not None:
        message["request_id"] = event.request_id
    return message
