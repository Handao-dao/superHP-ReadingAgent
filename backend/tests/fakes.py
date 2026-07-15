"""Small in-memory Ports used by application-layer tests."""

from typing import Any

from superhp_agent.contracts import BackendEvent, ReadingProgressSnapshot


class InMemoryReadingState:
    """Implement progress and event-log Ports without persistence."""

    def __init__(self) -> None:
        self.current_unit_id = ""
        self.opened_unit_ids: list[str] = []
        self.read_unit_ids: list[str] = []
        self.logged_events: list[dict[str, Any]] = []

    def load(self) -> ReadingProgressSnapshot:
        return ReadingProgressSnapshot(
            current_unit_id=self.current_unit_id,
            opened_unit_ids=list(self.opened_unit_ids),
            read_unit_ids=list(self.read_unit_ids),
        )

    def mark_opened(self, unit_id: str) -> ReadingProgressSnapshot:
        self.current_unit_id = unit_id
        if unit_id not in self.opened_unit_ids:
            self.opened_unit_ids.append(unit_id)
        return self.load()

    def mark_read(self, unit_id: str) -> ReadingProgressSnapshot:
        self.mark_opened(unit_id)
        if unit_id not in self.read_unit_ids:
            self.read_unit_ids.append(unit_id)
        return self.load()

    def log_event(self, event_type: str, **payload: Any) -> None:
        self.logged_events.append({"type": event_type, **payload})


class RecordingEventSink:
    """Capture transport-neutral backend events as assertion-friendly dicts."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def emit_event(self, event: BackendEvent) -> None:
        self.events.append(
            {"type": event.type, "request_id": event.request_id, **event.payload}
        )
