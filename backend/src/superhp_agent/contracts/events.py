"""Transport-neutral event data exchanged across backend boundaries.

This module describes an event that has already occurred. It does not deliver
events, choose subscribers, write logs, or know any HTTP/WebSocket message
format.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BackendEvent:
    """One observable backend event with optional request correlation."""

    type: str
    request_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
