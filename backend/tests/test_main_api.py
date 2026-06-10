from pathlib import Path

from superhp_agent import main
from superhp_agent.corpus import ReadingUnit
from superhp_agent.memory import ReadingMemory


class FakeMemoryStore:
    def load(self):
        return ReadingMemory(current_unit_id="hp01-ch01", read_unit_ids=["hp01-ch01"])


class FakeDB:
    def count_vocabulary_for_unit(self, unit_id: str) -> int:
        return 3 if unit_id == "hp01-ch01" else 0


class FakeSettings:
    def __init__(self, annotated_dir: Path):
        self.annotated_dir = annotated_dir


def test_unit_meta_includes_sidebar_status_fields(tmp_path, monkeypatch):
    annotated_dir = tmp_path / "annotated"
    annotated_dir.mkdir()
    (annotated_dir / "hp01-ch01.annotated.md").write_text("Annotated", encoding="utf-8")
    unit = ReadingUnit(
        id="hp01-ch01",
        chapter_id="hp01-ch01",
        book_id="hp01",
        book_title="Harry Potter and the Philosopher's Stone",
        chapter_no=1,
        chapter_title="The Boy Who Lived",
        section_no=1,
        section_count=1,
        summary="Summary",
        path=tmp_path / "hp01-ch01.md",
    )

    monkeypatch.setattr(main, "settings", FakeSettings(annotated_dir))
    monkeypatch.setattr(main, "memory_store", FakeMemoryStore())
    monkeypatch.setattr(main, "db", FakeDB())

    meta = main._unit_meta(unit)

    assert meta.status == "read"
    assert meta.has_annotated_copy is True
    assert meta.vocab_count == 3
