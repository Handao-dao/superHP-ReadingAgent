"""Persistence tests for reader-initiated lookup facts."""

from pathlib import Path

import pytest

from superhp_agent.contracts import ReadingLookupSummary
from superhp_agent.corpus import ReadingUnit
from superhp_agent.ports import ReadingLookupRepository
from superhp_agent.storage import AppDB
from superhp_agent.storage.sqlite import SQLiteReadingLookupRepository


def _unit(
    tmp_path: Path,
    *,
    unit_id: str = "hp01-ch01",
    chapter_id: str = "hp01-ch01",
) -> ReadingUnit:
    return ReadingUnit(
        id=unit_id,
        chapter_id=chapter_id,
        book_id="hp01",
        book_title="Harry Potter and the Philosopher's Stone",
        chapter_no=1,
        chapter_title="The Boy Who Lived",
        section_no=1,
        section_count=1,
        summary="",
        path=tmp_path / f"{unit_id}.md",
    )


def test_lookup_repository_records_and_summarizes_explicit_units(tmp_path):
    db = AppDB(tmp_path / "app.db")
    unit = _unit(tmp_path)
    second_unit = _unit(
        tmp_path,
        unit_id="hp01-ch02",
        chapter_id="hp01-ch02",
    )

    try:
        assert isinstance(db, ReadingLookupRepository)
        assert isinstance(
            db.reading_lookup_repository,
            SQLiteReadingLookupRepository,
        )

        db.record_lookup(unit, word="Wand")
        db.record_lookup(unit, word=" wand ", was_annotated=True)
        db.record_lookup(second_unit, word="spell")

        first_summary = db.summarize_lookups(unit_ids=[unit.id])
        assert first_summary == ReadingLookupSummary(
            lookup_count=2,
            unique_lookup_count=1,
            annotated_lookup_count=1,
        )
        assert first_summary.repeated_lookup_count == 1

        all_summary = db.summarize_lookups(
            unit_ids=[unit.id, second_unit.id, unit.id],
        )
        assert all_summary.lookup_count == 3
        assert all_summary.unique_lookup_count == 2
        assert all_summary.annotated_lookup_count == 1
        assert db.summarize_lookups(unit_ids=[]) == ReadingLookupSummary()
    finally:
        db.close()


def test_lookup_repository_rejects_blank_words(tmp_path):
    db = AppDB(tmp_path / "app.db")
    try:
        with pytest.raises(ValueError, match="word is required"):
            db.record_lookup(_unit(tmp_path), word=" ")
    finally:
        db.close()
