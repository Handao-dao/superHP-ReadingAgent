from fastapi.testclient import TestClient

from superhp_agent import main
from superhp_agent.artifacts import AnnotatedCopyStore
from superhp_agent.contracts import (
    ReadingDifficultyEvidence,
    ReadingDifficultyObservation,
    ReadingDifficultyState,
    ReadingProgressSnapshot,
)
from superhp_agent.corpus import CorpusError, ReadingUnit, ReadingUnitDocument
from superhp_agent.domain.reading_difficulty_prompt import (
    ReadingDifficultyPrompt,
    ReadingDifficultyPromptStatus,
)
from superhp_agent.library_catalog import CatalogBook, CatalogCollection


class FakeMemoryStore:
    def load(self):
        return ReadingProgressSnapshot(
            current_unit_id="hp01-ch01",
            read_unit_ids=["hp01-ch01"],
        )


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
            "paragraph_index": payload.get("paragraph_index", -1),
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
        self.units = [unit]

    def list_units(self):
        return self.units

    def get_unit(self, unit_id: str):
        if unit_id != self.unit.id:
            raise CorpusError(f"Unknown reading unit id: {unit_id}")
        return ReadingUnitDocument(meta=self.unit, body="Body")


class FakeLookupService:
    async def lookup(self, word: str, sentence: str, *, profile_id=None):
        return {
            "word": word,
            "word_cn": "魔杖",
            "pos": "noun",
            "sentence_cn": "他挥动了魔杖。",
        }


class FakeReadingLookupRepository:
    def __init__(self):
        self.calls = []

    def record_lookup(self, unit, *, word: str, was_annotated: bool = False):
        self.calls.append((unit.id, word, was_annotated))
        return len(self.calls)


class FailingReadingLookupRepository:
    def record_lookup(self, unit, *, word: str, was_annotated: bool = False):
        raise RuntimeError("storage unavailable")


class FakeReadingDifficultyMonitor:
    def observe_book(self, book_id):
        if book_id == "missing":
            raise ValueError("Unknown English book id: missing")
        return ReadingDifficultyObservation(
            book_id=book_id,
            state=ReadingDifficultyState.WATCHING,
            window_ready=True,
            observed_unit_ids=("book-1-ch01", "book-1-ch02", "book-1-ch03"),
            evidence=ReadingDifficultyEvidence(
                observed_word_count=6000,
                observed_chapter_count=3,
                lookup_density=11.0,
                unique_lookup_density=9.0,
                repeated_lookup_density=2.0,
                annotated_lookup_density=1.0,
            ),
        )


def _pending_prompt():
    return ReadingDifficultyPrompt(
        book_id="book-1",
        chapter_id="book-1-ch03",
        status=ReadingDifficultyPromptStatus.PENDING,
        evidence=ReadingDifficultyEvidence(
            observed_word_count=6000,
            observed_chapter_count=3,
            lookup_density=11,
            annotated_lookup_density=1,
            annotation_target=20,
        ),
    )


class FakeDifficultyPromptRepository:
    def get(self, book_id):
        return _pending_prompt() if book_id == "book-1" else None


class FakeDifficultyPromptCoordinator:
    def __init__(self):
        self.book_ids = []

    def choose_continue(self, book_id):
        self.book_ids.append(book_id)
        prompt = _pending_prompt()
        return ReadingDifficultyPrompt(
            book_id=prompt.book_id,
            chapter_id=prompt.chapter_id,
            status=ReadingDifficultyPromptStatus.CONTINUE_READING,
            evidence=prompt.evidence,
            cooldown_chapters_remaining=3,
            last_cooldown_chapter_id=prompt.chapter_id,
        )


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

    monkeypatch.setattr(main, "annotated_copies", AnnotatedCopyStore(annotated_dir))
    monkeypatch.setattr(main, "reading_progress_repository", FakeMemoryStore())
    monkeypatch.setattr(main, "vocabulary_repository", FakeDB())

    meta = main._unit_meta(unit)

    assert meta.status == "read"
    assert meta.has_annotated_copy is True
    assert meta.vocab_count == 3
    assert meta.profile_id == "english_novel"


def test_profile_api_lists_builtin_profiles():
    with TestClient(main.app) as client:
        response = client.get("/api/profiles")

    assert response.status_code == 200
    profile_ids = [item["id"] for item in response.json()]
    assert "english_novel" in profile_ids
    assert "classical_chinese" in profile_ids
    languages = {item["id"]: item["language_id"] for item in response.json()}
    assert languages == {"english_novel": "en", "classical_chinese": "lzh"}


def test_agent_http_routes_are_hidden_by_default():
    paths = {route.path for route in main.app.routes}

    assert main.settings.agent_features_enabled is False
    assert {
        "/api/recommendations/sessions",
        "/api/recommendations/difficulty-handoffs",
        "/api/recommendations/sessions/{session_id}/messages",
        "/api/recommendations/sessions/{session_id}",
        "/api/reading-companion/sessions",
        "/api/reading-companion/sessions/{session_id}/messages",
        "/api/reading-companion/sessions/{session_id}/retry",
        "/api/reading-companion/sessions/{session_id}",
    }.isdisjoint(paths)

    with TestClient(main.app) as client:
        recommendation = client.post("/api/recommendations/sessions")
        companion = client.post("/api/reading-companion/sessions")
        prompt = client.get("/api/reading-difficulty-prompts/book-1")
        openapi_paths = client.get("/openapi.json").json()["paths"]

    assert recommendation.status_code == 404
    assert companion.status_code == 404
    assert prompt.status_code == 404
    assert "/api/reading-difficulty-prompts/{book_id}" not in openapi_paths


def test_reading_difficulty_api_exposes_read_only_observation(monkeypatch):
    monkeypatch.setattr(
        main,
        "reading_difficulty_monitor",
        FakeReadingDifficultyMonitor(),
    )

    with TestClient(main.app) as client:
        response = client.get("/api/reading-difficulty/book-1")
        missing = client.get("/api/reading-difficulty/missing")

    assert response.status_code == 200
    assert response.json() == {
        "book_id": "book-1",
        "state": "watching",
        "window_ready": True,
        "observed_unit_ids": [
            "book-1-ch01",
            "book-1-ch02",
            "book-1-ch03",
        ],
        "evidence": {
            "observed_word_count": 6000,
            "observed_chapter_count": 3,
            "lookup_density": 11.0,
            "unique_lookup_density": 9.0,
            "repeated_lookup_density": 2.0,
            "annotated_lookup_density": 1.0,
        },
    }
    assert missing.status_code == 404


def test_difficulty_prompt_api_restores_and_records_continue_choice(
    monkeypatch,
):
    coordinator = FakeDifficultyPromptCoordinator()
    monkeypatch.setattr(
        main,
        "reading_difficulty_prompt_repository",
        FakeDifficultyPromptRepository(),
    )
    monkeypatch.setattr(
        main,
        "reading_difficulty_prompt_coordinator",
        coordinator,
    )
    monkeypatch.setattr(main.settings, "agent_features_enabled", True)

    with TestClient(main.app) as client:
        pending = client.get(
            "/api/reading-difficulty-prompts/book-1"
        )
        continued = client.post(
            "/api/reading-difficulty-prompts/book-1/continue"
        )
        missing = client.get(
            "/api/reading-difficulty-prompts/missing"
        )

    assert pending.status_code == 200
    assert pending.json()["status"] == "pending"
    assert pending.json()["evidence"]["annotation_target"] == 20
    assert continued.status_code == 200
    assert continued.json()["status"] == "continue_reading"
    assert continued.json()["cooldown_chapters_remaining"] == 3
    assert coordinator.book_ids == ["book-1"]
    assert missing.status_code == 404


def test_word_lookup_records_successful_click_with_reading_context(
    tmp_path,
    monkeypatch,
):
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
    repository = FakeReadingLookupRepository()
    monkeypatch.setattr(main, "corpus", FakeCorpus(unit))
    monkeypatch.setattr(main, "lookup_service", FakeLookupService())
    monkeypatch.setattr(main, "reading_lookup_repository", repository)

    with TestClient(main.app) as client:
        response = client.post(
            "/api/word-lookup",
            json={
                "word": "wand",
                "sentence": "He waved his wand.",
                "profile_id": "english_novel",
                "unit_id": unit.id,
                "was_annotated": True,
            },
        )

    assert response.status_code == 200
    assert response.json()["word_cn"] == "魔杖"
    assert repository.calls == [(unit.id, "wand", True)]


def test_word_lookup_rejects_unknown_context_unit_without_calling_provider(
    tmp_path,
    monkeypatch,
):
    unit = ReadingUnit(
        id="hp01-ch01",
        chapter_id="hp01-ch01",
        book_id="hp01",
        book_title="Book",
        chapter_no=1,
        chapter_title="Chapter",
        section_no=1,
        section_count=1,
        summary="",
        path=tmp_path / "hp01-ch01.md",
    )
    repository = FakeReadingLookupRepository()
    monkeypatch.setattr(main, "corpus", FakeCorpus(unit))
    monkeypatch.setattr(main, "lookup_service", FakeLookupService())
    monkeypatch.setattr(main, "reading_lookup_repository", repository)

    with TestClient(main.app) as client:
        response = client.post(
            "/api/word-lookup",
            json={
                "word": "wand",
                "profile_id": "english_novel",
                "unit_id": "missing",
            },
        )

    assert response.status_code == 404
    assert repository.calls == []


def test_word_lookup_result_survives_monitoring_storage_failure(
    tmp_path,
    monkeypatch,
):
    unit = ReadingUnit(
        id="hp01-ch01",
        chapter_id="hp01-ch01",
        book_id="hp01",
        book_title="Book",
        chapter_no=1,
        chapter_title="Chapter",
        section_no=1,
        section_count=1,
        summary="",
        path=tmp_path / "hp01-ch01.md",
    )
    monkeypatch.setattr(main, "corpus", FakeCorpus(unit))
    monkeypatch.setattr(main, "lookup_service", FakeLookupService())
    monkeypatch.setattr(
        main,
        "reading_lookup_repository",
        FailingReadingLookupRepository(),
    )

    with TestClient(main.app) as client:
        response = client.post(
            "/api/word-lookup",
            json={"word": "wand", "unit_id": unit.id},
        )

    assert response.status_code == 200
    assert response.json()["word_cn"] == "魔杖"


def test_profile_filtered_api_rejects_unknown_profile():
    with TestClient(main.app) as client:
        response = client.get("/api/units", params={"profile_id": "missing"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown profile id: missing"


def test_library_api_filters_collections_by_profile(monkeypatch):
    class FakeLibraryCatalog:
        def list_collections(self):
            return [
                CatalogCollection(
                    id="novels",
                    profile_id="english_novel",
                    title="Novels",
                    author="Author",
                    order=10,
                    books=(CatalogBook(id="book-1", order=1),),
                ),
                CatalogCollection(
                    id="classics",
                    profile_id="classical_chinese",
                    title="古文",
                    author="",
                    order=20,
                    books=(),
                ),
            ]

    monkeypatch.setattr(main, "library_catalog", FakeLibraryCatalog())
    with TestClient(main.app) as client:
        response = client.get("/api/library", params={"profile_id": "english_novel"})

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "novels",
            "profile_id": "english_novel",
            "title": "Novels",
            "author": "Author",
            "order": 10,
            "books": [{"id": "book-1", "order": 1}],
        }
    ]


def test_list_units_can_filter_by_profile(tmp_path, monkeypatch):
    english = ReadingUnit(
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
        profile_id="english_novel",
    )
    classical = ReadingUnit(
        id="cc-lunyu-xueer-01",
        chapter_id="cc-lunyu-xueer-01",
        book_id="cc-lunyu",
        book_title="论语",
        chapter_no=1,
        chapter_title="学而",
        section_no=1,
        section_count=1,
        summary="Summary",
        path=tmp_path / "lunyu-xueer.md",
        profile_id="classical_chinese",
    )
    fake_corpus = FakeCorpus(english)
    fake_corpus.units = [english, classical]
    monkeypatch.setattr(main, "corpus", fake_corpus)
    monkeypatch.setattr(main, "reading_progress_repository", FakeMemoryStore())
    monkeypatch.setattr(main, "vocabulary_repository", FakeDB())
    monkeypatch.setattr(main, "annotated_copies", AnnotatedCopyStore(tmp_path / "annotated"))

    with TestClient(main.app) as client:
        response = client.get("/api/units", params={"profile_id": "classical_chinese"})

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload] == ["cc-lunyu-xueer-01"]


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
    monkeypatch.setattr(main, "bookmark_repository", fake_db)

    with TestClient(main.app) as client:
        created = client.post(
            "/api/bookmarks",
            json={
                "unit_id": "hp01-ch01",
                "body_kind": "annotated",
                "page_index": 2,
                "progress_ratio": 0.25,
                "total_pages": 8,
                "label": "Chapter 1 · Page 3",
                "excerpt": "Mr and Mrs Dursley...",
                "paragraph_index": 7,
            },
        )
        assert created.status_code == 200
        assert created.json()["id"] == 1
        assert created.json()["body_kind"] == "annotated"
        assert created.json()["paragraph_index"] == 7

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
    monkeypatch.setattr(main, "bookmark_repository", FakeDB())

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
