"""Tests for the append-only event log boundary."""

import json

from superhp_agent.event_log import EventLogStore


def test_event_log_appends_utf8_json_lines(tmp_path):
    path = tmp_path / "memory" / "events.jsonl"
    store = EventLogStore(path)

    store.log_event("unit_opened", unit_id="论语-01")
    store.log_event("session_disconnected")

    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert events[0]["type"] == "unit_opened"
    assert events[0]["unit_id"] == "论语-01"
    assert events[0]["created_at"]
    assert events[1]["type"] == "session_disconnected"
