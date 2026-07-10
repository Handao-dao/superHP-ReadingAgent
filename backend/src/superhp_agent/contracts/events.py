"""Transport-neutral event data exchanged across backend boundaries.

This module describes an event that has already occurred. It does not deliver
events, choose subscribers, or write logs. ``as_message`` temporarily preserves
the existing flat frontend JSON shape until Transport DTOs are separated.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BackendEvent:
    """One observable backend event with optional request correlation."""

    type: str
    request_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def as_message(self) -> dict[str, Any]:
        """Convert to the flat JSON shape currently used by the frontend."""
        message = {"type": self.type, **self.payload}
        if self.request_id is not None:
            message["request_id"] = self.request_id
        return message
