import json

from superhp_agent.memory import ReadingMemoryStore


def test_empty_memory_defaults_to_empty_state(tmp_path):
    store = ReadingMemoryStore(tmp_path / "reading_memory.json", tmp_path / "events.jsonl")

    memory = store.load()

    assert memory.current_unit_id == ""
    assert memory.opened_unit_ids == []
    assert memory.read_unit_ids == []


def test_mark_opened_persists_current_unit_and_event(tmp_path):
    store = ReadingMemoryStore(tmp_path / "reading_memory.json", tmp_path / "events.jsonl")

    store.mark_opened("hp01-ch01")
    memory = store.load()

    assert memory.current_unit_id == "hp01-ch01"
    assert memory.opened_unit_ids == ["hp01-ch01"]

    events = (tmp_path / "events.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(events[-1])["type"] == "unit_opened"


def test_mark_read_is_idempotent(tmp_path):
    store = ReadingMemoryStore(tmp_path / "reading_memory.json", tmp_path / "events.jsonl")

    store.mark_read("hp01-ch01")
    store.mark_read("hp01-ch01")
    memory = store.load()

    assert memory.opened_unit_ids == ["hp01-ch01"]
    assert memory.read_unit_ids == ["hp01-ch01"]
