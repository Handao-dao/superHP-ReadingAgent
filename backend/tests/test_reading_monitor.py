"""Deterministic tests for long-window reading difficulty observations."""

from pathlib import Path

import pytest

from superhp_agent.application import (
    ReadingDifficultyMonitor,
    ReadingDifficultyPolicy,
)
from superhp_agent.contracts import (
    ReadingDifficultyState,
    ReadingLookupSummary,
    ReadingProgressSnapshot,
)
from superhp_agent.corpus import ReadingUnit, ReadingUnitDocument


class FakeCorpus:
    def __init__(self, documents):
        self.documents = {document.meta.id: document for document in documents}

    def list_units(self):
        return [document.meta for document in self.documents.values()]

    def get_unit(self, unit_id):
        return self.documents[unit_id]


class FakeProgressRepository:
    def __init__(self, read_unit_ids):
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


def _document(
    tmp_path: Path,
    *,
    unit_id: str,
    chapter_id: str,
    chapter_no: int,
    word_count: int,
    book_id: str = "book-1",
) -> ReadingUnitDocument:
    unit = ReadingUnit(
        id=unit_id,
        chapter_id=chapter_id,
        book_id=book_id,
        book_title="A Book",
        chapter_no=chapter_no,
        chapter_title=f"Chapter {chapter_no}",
        section_no=1,
        section_count=1,
        summary="",
        path=tmp_path / f"{unit_id}.md",
    )
    body = " ".join(
        "can't" if index == 0 else f"word{index}"
        for index in range(word_count)
    )
    return ReadingUnitDocument(meta=unit, body=body)


def test_monitor_enters_watching_only_for_ready_high_density_window(tmp_path):
    documents = [
        _document(
            tmp_path,
            unit_id=f"book-1-ch{chapter_no}",
            chapter_id=f"book-1-ch{chapter_no}",
            chapter_no=chapter_no,
            word_count=2000,
        )
        for chapter_no in range(1, 4)
    ]
    lookup_repository = FakeLookupRepository(
        ReadingLookupSummary(
            lookup_count=220,
            unique_lookup_count=180,
            annotated_lookup_count=20,
        )
    )
    monitor = ReadingDifficultyMonitor(
        FakeCorpus(documents),
        FakeProgressRepository([document.meta.id for document in documents]),
        lookup_repository,
    )

    observation = monitor.observe_book("book-1")

    assert observation.state is ReadingDifficultyState.WATCHING
    assert observation.window_ready is True
    assert observation.evidence.observed_word_count == 6000
    assert observation.evidence.observed_chapter_count == 3
    assert observation.evidence.lookup_density == 11.0
    assert observation.evidence.unique_lookup_density == 9.0
    assert observation.evidence.repeated_lookup_density == 2.0
    assert observation.evidence.annotated_lookup_density == 1.0
    assert lookup_repository.requested_unit_ids == observation.observed_unit_ids


def test_monitor_keeps_insufficient_high_density_data_normal(tmp_path):
    documents = [
        _document(
            tmp_path,
            unit_id=f"book-1-ch{chapter_no}",
            chapter_id=f"book-1-ch{chapter_no}",
            chapter_no=chapter_no,
            word_count=3000,
        )
        for chapter_no in range(1, 3)
    ]
    monitor = ReadingDifficultyMonitor(
        FakeCorpus(documents),
        FakeProgressRepository([document.meta.id for document in documents]),
        FakeLookupRepository(
            ReadingLookupSummary(
                lookup_count=300,
                unique_lookup_count=250,
                annotated_lookup_count=20,
            )
        ),
    )

    observation = monitor.observe_book("book-1")

    assert observation.evidence.lookup_density == 15.0
    assert observation.window_ready is False
    assert observation.state is ReadingDifficultyState.NORMAL


def test_monitor_uses_completed_units_and_distinct_chapter_ids(tmp_path):
    documents = [
        _document(
            tmp_path,
            unit_id="book-1-ch1-sec1",
            chapter_id="book-1-ch1",
            chapter_no=1,
            word_count=1500,
        ),
        _document(
            tmp_path,
            unit_id="book-1-ch1-sec2",
            chapter_id="book-1-ch1",
            chapter_no=1,
            word_count=1500,
        ),
        _document(
            tmp_path,
            unit_id="book-1-ch2",
            chapter_id="book-1-ch2",
            chapter_no=2,
            word_count=2500,
        ),
        _document(
            tmp_path,
            unit_id="book-1-ch3-unread",
            chapter_id="book-1-ch3",
            chapter_no=3,
            word_count=2500,
        ),
    ]
    completed_ids = [document.meta.id for document in documents[:3]]
    monitor = ReadingDifficultyMonitor(
        FakeCorpus(documents),
        FakeProgressRepository(completed_ids),
        FakeLookupRepository(ReadingLookupSummary()),
    )

    observation = monitor.observe_book("book-1")

    assert observation.observed_unit_ids == tuple(completed_ids)
    assert observation.evidence.observed_word_count == 5500
    assert observation.evidence.observed_chapter_count == 2
    assert observation.window_ready is False


def test_monitor_treats_threshold_as_normal_and_rejects_unknown_book(tmp_path):
    documents = [
        _document(
            tmp_path,
            unit_id=f"book-1-ch{chapter_no}",
            chapter_id=f"book-1-ch{chapter_no}",
            chapter_no=chapter_no,
            word_count=2000,
        )
        for chapter_no in range(1, 4)
    ]
    monitor = ReadingDifficultyMonitor(
        FakeCorpus(documents),
        FakeProgressRepository([document.meta.id for document in documents]),
        FakeLookupRepository(
            ReadingLookupSummary(
                lookup_count=200,
                unique_lookup_count=180,
                annotated_lookup_count=10,
            )
        ),
        policy=ReadingDifficultyPolicy(watching_lookups_per_300=10),
    )

    assert monitor.observe_book("book-1").state is ReadingDifficultyState.NORMAL
    with pytest.raises(ValueError, match="Unknown English book id"):
        monitor.observe_book("missing")
