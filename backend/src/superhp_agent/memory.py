"""File-backed reading memory and event log."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class ReadingMemory:
    current_unit_id: str = ""
    opened_unit_ids: list[str] = field(default_factory=list)
    read_unit_ids: list[str] = field(default_factory=list)
    annotated_unit_ids: list[str] = field(default_factory=list)
    updated_at: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReadingMemory:
        return cls(
            current_unit_id=str(data.get("current_unit_id") or ""),
            opened_unit_ids=_string_list(data.get("opened_unit_ids")),
            read_unit_ids=_string_list(data.get("read_unit_ids")),
            annotated_unit_ids=_string_list(data.get("annotated_unit_ids")),
            updated_at=str(data.get("updated_at") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_unit_id": self.current_unit_id,
            "opened_unit_ids": self.opened_unit_ids,
            "read_unit_ids": self.read_unit_ids,
            "annotated_unit_ids": self.annotated_unit_ids,
            "updated_at": self.updated_at,
        }


class ReadingMemoryStore:
    """Persist product memory as JSON and append behavior events as JSONL."""

    def __init__(self, memory_path: str | Path, event_log_path: str | Path):
        self.memory_path = Path(memory_path)
        self.event_log_path = Path(event_log_path)
        self.memory_path.parent.mkdir(parents=True, exist_ok=True)
        self.event_log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def load(self) -> ReadingMemory:
        with self._lock:
            if not self.memory_path.exists() or self.memory_path.stat().st_size == 0:
                return ReadingMemory()
            raw = self.memory_path.read_text(encoding="utf-8").strip()
            if not raw:
                return ReadingMemory()
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("reading memory must be a JSON object")
            return ReadingMemory.from_dict(data)

    def save(self, memory: ReadingMemory) -> None:
        with self._lock:
            memory.updated_at = utc_now()
            self.memory_path.write_text(
                json.dumps(memory.to_dict(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

    def mark_opened(self, unit_id: str) -> ReadingMemory:
        memory = self.load()
        memory.current_unit_id = unit_id
        memory.opened_unit_ids = _append_unique(memory.opened_unit_ids, unit_id)
        self.save(memory)
        self.log_event("unit_opened", unit_id=unit_id)
        return memory

    def mark_read(self, unit_id: str) -> ReadingMemory:
        memory = self.load()
        memory.current_unit_id = unit_id
        memory.opened_unit_ids = _append_unique(memory.opened_unit_ids, unit_id)
        memory.read_unit_ids = _append_unique(memory.read_unit_ids, unit_id)
        self.save(memory)
        self.log_event("unit_marked_read", unit_id=unit_id)
        return memory

    def mark_annotated(self, unit_id: str) -> ReadingMemory:
        memory = self.load()
        memory.annotated_unit_ids = _append_unique(memory.annotated_unit_ids, unit_id)
        self.save(memory)
        self.log_event("unit_marked_annotated", unit_id=unit_id)
        return memory

    def log_event(self, event_type: str, **payload: Any) -> None:
        event = {
            "type": event_type,
            "created_at": utc_now(),
            **payload,
        }
        with self._lock:
            with self.event_log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def _append_unique(items: list[str], value: str) -> list[str]:
    if value in items:
        return items
    return [*items, value]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]