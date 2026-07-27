"""Persistence tests for per-book annotation support targets."""

import pytest

from superhp_agent.domain.reading_support import ReadingSupportState
from superhp_agent.ports import ReadingSupportRepository
from superhp_agent.storage import AppDB
from superhp_agent.storage.sqlite import SQLiteReadingSupportRepository


def test_reading_support_defaults_and_isolates_book_targets(tmp_path):
    db = AppDB(tmp_path / "app.db")

    try:
        assert isinstance(db, ReadingSupportRepository)
        assert isinstance(
            db.reading_support_repository,
            SQLiteReadingSupportRepository,
        )
        assert db.get_annotation_target("book-1") == 8
        assert db.get_annotation_target("book-2") == 8

        db.set_annotation_target("book-1", 14)

        assert db.get_annotation_target("book-1") == 14
        assert db.get_annotation_target("book-2") == 8
        assert db.get_state("book-1").cooldown_chapters_remaining == 3
        assert db.get_state("book-2") == ReadingSupportState()
    finally:
        db.close()


def test_reading_support_persists_per_book_evaluation_state(tmp_path):
    db = AppDB(tmp_path / "app.db")
    state = ReadingSupportState(
        annotation_target=8,
        low_density_streak=1,
        last_evaluated_chapter_id="book-1-ch03",
        last_decision="shadow:hold",
        last_uncovered_lookup_density=5.5,
    )

    try:
        db.save_evaluation_state("book-1", state)

        stored = db.get_state("book-1")
        assert stored.annotation_target == 8
        assert stored.low_density_streak == 1
        assert stored.last_evaluated_chapter_id == "book-1-ch03"
        assert stored.last_decision == "shadow:hold"
        assert stored.last_uncovered_lookup_density == 5.5
        assert stored.updated_at
        assert db.get_state("book-2") == ReadingSupportState()
    finally:
        db.close()


@pytest.mark.parametrize("target", [0, 21, 8.5, True])
def test_reading_support_rejects_invalid_targets(tmp_path, target):
    db = AppDB(tmp_path / "app.db")
    try:
        with pytest.raises(ValueError, match="annotation_target"):
            db.set_annotation_target("book-1", target)
    finally:
        db.close()


def test_reading_support_rejects_blank_book_id(tmp_path):
    db = AppDB(tmp_path / "app.db")
    try:
        with pytest.raises(ValueError, match="book_id is required"):
            db.get_annotation_target(" ")
    finally:
        db.close()
