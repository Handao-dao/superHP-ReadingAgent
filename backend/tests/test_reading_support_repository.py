"""Persistence tests for per-book annotation support targets."""

import pytest

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
