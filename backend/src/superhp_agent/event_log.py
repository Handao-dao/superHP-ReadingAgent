"""Append-only behavior event logging.

This module owns diagnostic and product-event records only. Reading progress is
durable business state and belongs to ``ReadingProgressRepository`` instead.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class EventLogStore:
    """Append structured events to a UTF-8 JSONL file."""

    def __init__(self, event_log_path: str | Path):
        self.event_log_path = Path(event_log_path)
        self.event_log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def log_event(self, event_type: str, **payload: Any) -> None:
        """Append one event without reading or mutating application state."""
        event = {
            "type": event_type,
            "created_at": datetime.now(UTC).isoformat(),
            **payload,
        }
        with self._lock:
            with self.event_log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")
