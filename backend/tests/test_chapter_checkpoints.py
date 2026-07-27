"""Chapter-completion checkpoint recording and persistence tests."""

from pathlib import Path

from superhp_agent.application import ChapterCheckpointRecorder
from superhp_agent.artifacts import AnnotatedCopyStore
from superhp_agent.contracts import (
    ChapterReadingCheckpoint,
    ReadingLookupSummary,
    ReadingProgressSnapshot,
)
from superhp_agent.corpus import ReadingUnit, ReadingUnitDocument
from superhp_agent.ports import ChapterReadingCheckpointRepository
from superhp_agent.storage import AppDB
from superhp_agent.storage.sqlite import (
    SQLiteChapterReadingCheckpointRepository,
)


class FakeCorpus:
    def __init__(self, documents):
        self.documents = {document.meta.id: document for document in documents}

    def list_units(self):
        return [document.meta for document in self.documents.values()]

    def get_unit(self, unit_id):
        return self.documents[unit_id]


class FakeProgressRepository:
    def __init__(self, read_unit_ids=()):
        self.read_unit_ids = list(read_unit_ids)

    def load(self):
        return ReadingProgressSnapshot(read_unit_ids=list(self.read_unit_ids))


class FakeLookupRepository:
    def __init__(self, summary):
        self.summary = summary
        self.requested_unit_ids = ()

    def summarize_lookups(self, *, unit_ids):
        self.requested_unit_ids = tuple(unit_ids)
        return self.summary


class FakeCheckpointRepository:
    def __init__(self):
        self.checkpoints = {}

    def record(self, checkpoint):
        key = (checkpoint.book_id, checkpoint.chapter_id)
        if key in self.checkpoints:
            return None
        self.checkpoints[key] = checkpoint
        return checkpoint

    def list_for_book(self, book_id):
        return tuple(
            checkpoint
            for (stored_book_id, _), checkpoint in self.checkpoints.items()
            if stored_book_id == book_id
        )


def _document(
    tmp_path: Path,
    *,
    unit_id: str,
    section_no: int,
    body: str,
    language_id: str = "en",
) -> ReadingUnitDocument:
    unit = ReadingUnit(
        id=unit_id,
        chapter_id="book-1-ch01",
        book_id="book-1",
        book_title="Book One",
        chapter_no=1,
        chapter_title="Chapter One",
        section_no=section_no,
        section_count=2,
        summary="",
        path=tmp_path / f"{unit_id}.md",
        profile_id="english_novel",
        language_id=language_id,
    )
    return ReadingUnitDocument(meta=unit, body=body)


def test_recorder_waits_for_every_unit_then_records_chapter_once(tmp_path):
    documents = [
        _document(
            tmp_path,
            unit_id="book-1-ch01-sec1",
            section_no=1,
            body="One two three.",
        ),
        _document(
            tmp_path,
            unit_id="book-1-ch01-sec2",
            section_no=2,
            body="Four can't five.",
        ),
    ]
    progress = FakeProgressRepository([documents[0].meta.id])
    lookups = FakeLookupRepository(
        ReadingLookupSummary(
            lookup_count=5,
            unique_lookup_count=4,
            annotated_lookup_count=2,
        )
    )
    repository = FakeCheckpointRepository()
    annotated_copies = AnnotatedCopyStore(tmp_path / "annotated")
    for document in documents:
        annotated_copies.write(
            document,
            annotated_text=document.body,
            vocabulary=[],
            annotation_target=10,
        )
    recorder = ChapterCheckpointRecorder(
        FakeCorpus(documents),
        progress,
        lookups,
        repository,
        annotated_copies,
    )

    assert recorder.record_if_complete(documents[0].meta.id) is None
    assert lookups.requested_unit_ids == ()

    progress.read_unit_ids.append(documents[1].meta.id)
    checkpoint = recorder.record_if_complete(documents[1].meta.id)

    assert checkpoint is not None
    assert checkpoint.unit_ids == tuple(
        document.meta.id for document in documents
    )
    assert checkpoint.word_count == 6
    assert checkpoint.lookup_count == 5
    assert checkpoint.annotated_lookup_count == 2
    assert checkpoint.annotation_target == 10
    assert lookups.requested_unit_ids == checkpoint.unit_ids
    assert recorder.record_if_complete(documents[1].meta.id) is None
    assert len(repository.checkpoints) == 1


def test_recorder_uses_none_when_actual_chapter_target_is_not_consistent(tmp_path):
    documents = [
        _document(
            tmp_path,
            unit_id="book-1-ch01-sec1",
            section_no=1,
            body="One.",
        ),
        _document(
            tmp_path,
            unit_id="book-1-ch01-sec2",
            section_no=2,
            body="Two.",
        ),
    ]
    annotated_copies = AnnotatedCopyStore(tmp_path / "annotated")
    annotated_copies.write(
        documents[0],
        annotated_text="One.",
        vocabulary=[],
        annotation_target=8,
    )
    annotated_copies.write(
        documents[1],
        annotated_text="Two.",
        vocabulary=[],
        annotation_target=10,
    )
    recorder = ChapterCheckpointRecorder(
        FakeCorpus(documents),
        FakeProgressRepository(document.meta.id for document in documents),
        FakeLookupRepository(ReadingLookupSummary()),
        FakeCheckpointRepository(),
        annotated_copies,
    )

    checkpoint = recorder.record_if_complete(documents[1].meta.id)

    assert checkpoint is not None
    assert checkpoint.annotation_target is None


def test_recorder_ignores_non_english_chapter(tmp_path):
    document = _document(
        tmp_path,
        unit_id="book-1-ch01",
        section_no=1,
        body="学而时习之。",
        language_id="lzh",
    )
    recorder = ChapterCheckpointRecorder(
        FakeCorpus([document]),
        FakeProgressRepository([document.meta.id]),
        FakeLookupRepository(ReadingLookupSummary()),
        FakeCheckpointRepository(),
        AnnotatedCopyStore(tmp_path / "annotated"),
    )

    assert recorder.record_if_complete(document.meta.id) is None


def test_sqlite_checkpoint_repository_is_idempotent_and_book_scoped(tmp_path):
    db = AppDB(tmp_path / "app.db")
    checkpoint = ChapterReadingCheckpoint(
        book_id="book-1",
        chapter_id="book-1-ch01",
        chapter_no=1,
        unit_ids=("book-1-ch01-sec1", "book-1-ch01-sec2"),
        word_count=5000,
        lookup_count=10,
        annotated_lookup_count=2,
        annotation_target=8,
    )

    try:
        repository = db.chapter_checkpoint_repository
        assert isinstance(repository, SQLiteChapterReadingCheckpointRepository)
        assert isinstance(repository, ChapterReadingCheckpointRepository)

        stored = repository.record(checkpoint)

        assert stored is not None
        assert stored.completed_at
        assert repository.record(checkpoint) is None
        assert repository.list_for_book("book-1") == (stored,)
        assert repository.list_for_book("book-2") == ()
    finally:
        db.close()
