"""Tests for the trusted completed-chapter scope used by Agent tools."""

from pathlib import Path

import pytest

from superhp_agent.application import PreviousReadingScopeBuilder
from superhp_agent.contracts import ChapterReadingCheckpoint
from superhp_agent.corpus import ReadingUnit


class FakeCorpus:
    def __init__(self, units):
        self.units = tuple(units)

    def list_units(self):
        return list(self.units)


class FakeCheckpointRepository:
    def __init__(self, checkpoints):
        self.checkpoints = tuple(checkpoints)
        self.requested_book_id = ""

    def list_for_book(self, book_id):
        self.requested_book_id = book_id
        return self.checkpoints


def _unit(
    *,
    unit_id: str,
    chapter_no: int,
    section_no: int = 1,
    book_id: str = "book-1",
    chapter_id: str | None = None,
) -> ReadingUnit:
    chapter_id = chapter_id or f"{book_id}-ch{chapter_no:02d}"
    return ReadingUnit(
        id=unit_id,
        chapter_id=chapter_id,
        book_id=book_id,
        book_title=f"Book {book_id}",
        chapter_no=chapter_no,
        chapter_title=f"Chapter {chapter_no}",
        section_no=section_no,
        section_count=1,
        summary="",
        path=Path(f"{unit_id}.md"),
    )


def _checkpoint(
    *,
    chapter_no: int,
    unit_ids: tuple[str, ...],
    book_id: str = "book-1",
    chapter_id: str | None = None,
) -> ChapterReadingCheckpoint:
    return ChapterReadingCheckpoint(
        book_id=book_id,
        chapter_id=chapter_id or f"{book_id}-ch{chapter_no:02d}",
        chapter_no=chapter_no,
        unit_ids=unit_ids,
        word_count=1000,
        lookup_count=0,
        annotated_lookup_count=0,
    )


def test_builder_returns_prior_checkpointed_chapters_in_corpus_order():
    units = (
        _unit(unit_id="ch1-sec2", chapter_no=1, section_no=2),
        _unit(unit_id="ch3-sec1", chapter_no=3),
        _unit(unit_id="ch1-sec1", chapter_no=1, section_no=1),
        _unit(unit_id="ch2-sec1", chapter_no=2),
        _unit(unit_id="ch4-sec1", chapter_no=4),
        _unit(
            unit_id="other-ch1",
            chapter_no=1,
            book_id="book-2",
        ),
    )
    repository = FakeCheckpointRepository(
        (
            _checkpoint(chapter_no=2, unit_ids=("ch2-sec1",)),
            _checkpoint(
                chapter_no=1,
                unit_ids=("ch1-sec2", "ch1-sec1"),
            ),
            _checkpoint(chapter_no=3, unit_ids=("ch3-sec1",)),
            _checkpoint(chapter_no=4, unit_ids=("ch4-sec1",)),
            _checkpoint(
                chapter_no=1,
                unit_ids=("other-ch1",),
                book_id="book-2",
            ),
        )
    )

    scope = PreviousReadingScopeBuilder(
        FakeCorpus(units),
        repository,
    ).build("ch3-sec1")

    assert scope.book_id == "book-1"
    assert scope.current_chapter_id == "book-1-ch03"
    assert scope.current_chapter_no == 3
    assert [
        chapter.chapter_id for chapter in scope.completed_chapters
    ] == ["book-1-ch01", "book-1-ch02"]
    assert scope.completed_chapters[0].unit_ids == (
        "ch1-sec1",
        "ch1-sec2",
    )
    assert repository.requested_book_id == "book-1"


def test_builder_excludes_stale_or_incomplete_checkpoint_units():
    units = (
        _unit(unit_id="ch1-sec1", chapter_no=1, section_no=1),
        _unit(unit_id="ch1-sec2", chapter_no=1, section_no=2),
        _unit(unit_id="ch2-sec1", chapter_no=2),
    )
    repository = FakeCheckpointRepository(
        (
            _checkpoint(chapter_no=1, unit_ids=("ch1-sec1",)),
        )
    )

    scope = PreviousReadingScopeBuilder(
        FakeCorpus(units),
        repository,
    ).build("ch2-sec1")

    assert scope.completed_chapters == ()
    assert scope.searchable_unit_ids == ()


def test_builder_excludes_the_entire_current_chapter():
    units = (
        _unit(unit_id="ch1-sec1", chapter_no=1),
        _unit(unit_id="ch2-sec1", chapter_no=2, section_no=1),
        _unit(unit_id="ch2-sec2", chapter_no=2, section_no=2),
    )
    repository = FakeCheckpointRepository(
        (
            _checkpoint(chapter_no=1, unit_ids=("ch1-sec1",)),
            _checkpoint(
                chapter_no=2,
                unit_ids=("ch2-sec1", "ch2-sec2"),
            ),
        )
    )

    scope = PreviousReadingScopeBuilder(
        FakeCorpus(units),
        repository,
    ).build("ch2-sec2")

    assert scope.searchable_unit_ids == ("ch1-sec1",)


@pytest.mark.parametrize("current_unit_id", ["", "missing"])
def test_builder_rejects_a_missing_current_reading_unit(current_unit_id):
    builder = PreviousReadingScopeBuilder(
        FakeCorpus((_unit(unit_id="ch1", chapter_no=1),)),
        FakeCheckpointRepository(()),
    )

    with pytest.raises(ValueError):
        builder.build(current_unit_id)
