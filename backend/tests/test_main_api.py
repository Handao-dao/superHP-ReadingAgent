from pathlib import Path

from fastapi.testclient import TestClient

from superhp_agent import main
from superhp_agent.corpus import CorpusError, ReadingUnit, ReadingUnitDocument
from superhp_agent.memory import ReadingMemory


class FakeMemoryStore:
    def load(self):
        return ReadingMemory(current_unit_id="hp01-ch01", read_unit_ids=["hp01-ch01"])


class FakeDB:
    def __init__(self):
        self.rows = []
        self.next_id = 1

    def count_vocabulary_for_unit(self, unit_id: str) -> int:
        return 3 if unit_id == "hp01-ch01" else 0

    def add_bookmark(self, unit, **payload):
        bookmark_id = self.next_id
        self.next_id += 1
        self.rows.insert(0, {
            "id": bookmark_id,
            "unit_id": unit.id,
            "chapter_id": unit.chapter_id,
            "body_kind": payload["body_kind"],
            "page_index": payload["page_index"],
            "progress_ratio": payload.get("progress_ratio", 0),
            "total_pages": payload.get("total_pages", 0),
            "label": payload.get("label", ""),
            "excerpt": payload.get("excerpt", ""),
            "created_at": "2026-06-11 10:00:00",
        })
        return bookmark_id

    def list_bookmarks(self, unit_id=None):
        if unit_id:
            return [row for row in self.rows if row["unit_id"] == unit_id]
        return list(self.rows)

    def delete_bookmark(self, bookmark_id: int) -> bool:
        before = len(self.rows)
        self.rows = [row for row in self.rows if row["id"] != bookmark_id]
        return len(self.rows) != before


class FakeCorpus:
    def __init__(self, unit: ReadingUnit):
        self.unit = unit

    def get_unit(self, unit_id: str):
        if unit_id != self.unit.id:
            raise CorpusError(f"Unknown reading unit id: {unit_id}")
        return ReadingUnitDocument(meta=self.unit, body="Body")


class FakeSettings:
    def __init__(self, annotated_dir: Path):
        self.annotated_dir = annotated_dir


def test_unit_meta_includes_sidebar_status_fields(tmp_path, monkeypatch):
    annotated_dir = tmp_path / "annotated"
    annotated_dir.mkdir()
    (annotated_dir / "hp01-ch01.advanced.annotated.md").write_text("Annotated", encoding="utf-8")
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
    assert meta.profile_id == "english_novel"


def test_bookmark_api_create_list_and_delete(tmp_path, monkeypatch):
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
    fake_db = FakeDB()
    monkeypatch.setattr(main, "corpus", FakeCorpus(unit))
    monkeypatch.setattr(main, "db", fake_db)

    with TestClient(main.app) as client:
        created = client.post(
            "/api/bookmarks",
            json={
                "unit_id": "hp01-ch01",
                "body_kind": "source",
                "page_index": 2,
                "progress_ratio": 0.25,
                "total_pages": 8,
                "label": "Chapter 1 · Page 3",
                "excerpt": "Mr and Mrs Dursley...",
            },
        )
        assert created.status_code == 200
        assert created.json()["id"] == 1
        assert created.json()["body_kind"] == "source"

        listed = client.get("/api/bookmarks", params={"unit_id": "hp01-ch01"})
        assert listed.status_code == 200
        assert listed.json()[0]["label"] == "Chapter 1 · Page 3"

        deleted = client.delete("/api/bookmarks/1")
        assert deleted.status_code == 200
        assert client.get("/api/bookmarks").json() == []


def test_bookmark_api_rejects_bad_unit_and_body_kind(tmp_path, monkeypatch):
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
    monkeypatch.setattr(main, "corpus", FakeCorpus(unit))
    monkeypatch.setattr(main, "db", FakeDB())

    with TestClient(main.app) as client:
        bad_kind = client.post(
            "/api/bookmarks",
            json={"unit_id": "hp01-ch01", "body_kind": "notes", "page_index": 0},
        )
        assert bad_kind.status_code == 400

        bad_unit = client.post(
            "/api/bookmarks",
            json={"unit_id": "missing", "body_kind": "source", "page_index": 0},
        )
        assert bad_unit.status_code == 404

        missing_delete = client.delete("/api/bookmarks/404")
        assert missing_delete.status_code == 404
