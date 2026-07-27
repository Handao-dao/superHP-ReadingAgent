"""Tests for server-owned construction of recommendation handoff context."""

from pathlib import Path

import pytest

from superhp_agent.application.difficulty_handoff import (
    DifficultyHandoffBookNotFoundError,
    DifficultyRecommendationHandoffBuilder,
)
from superhp_agent.contracts import (
    BookCandidate,
    BookDifficulty,
    BookEntryKind,
    ReadingDifficultyEvidence,
    ReadingProgressSnapshot,
)
from superhp_agent.corpus import ReadingUnit
from superhp_agent.library_catalog import CatalogBook, CatalogCollection


def _unit(unit_id: str, chapter_no: int) -> ReadingUnit:
    return ReadingUnit(
        id=unit_id,
        chapter_id=unit_id,
        book_id="hp01",
        book_title="Harry Potter and the Philosopher's Stone",
        chapter_no=chapter_no,
        chapter_title=f"Chapter {chapter_no}",
        section_no=1,
        section_count=1,
        summary="",
        path=Path(f"{unit_id}.md"),
    )


class FakeCorpus:
    def list_units(self):
        return [_unit("hp01-ch01", 1), _unit("hp01-ch02", 2)]


class FakeLibraryCatalog:
    def collection_for_book(self, book_id):
        if book_id != "hp01":
            return None
        return CatalogCollection(
            id="harry-potter",
            profile_id="english_novel",
            title="Harry Potter",
            author="J. K. Rowling",
            order=1,
            books=(CatalogBook(id="hp01", order=1),),
        )


class FakeDifficultyCatalog:
    def __init__(self):
        self.candidate = BookCandidate(
            catalog_id="harry-potter",
            title_en="Harry Potter",
            title_zh="哈利·波特",
            author="J. K. Rowling",
            entry_kind=BookEntryKind.SERIES,
            difficulty=BookDifficulty(880, 940),
            genres=("fantasy", "adventure"),
        )

    async def find_by_id(self, catalog_id):
        return (
            self.candidate
            if catalog_id == self.candidate.catalog_id
            else None
        )

    async def search_books(self, query):
        return [self.candidate]


class FakeProgressRepository:
    def load(self):
        return ReadingProgressSnapshot(read_unit_ids=["hp01-ch01"])


def _builder():
    return DifficultyRecommendationHandoffBuilder(
        FakeCorpus(),
        FakeLibraryCatalog(),
        FakeDifficultyCatalog(),
        FakeProgressRepository(),
    )


@pytest.mark.asyncio
async def test_handoff_joins_book_metadata_progress_and_lower_target_band():
    evidence = ReadingDifficultyEvidence(
        observed_word_count=7200,
        observed_chapter_count=3,
        lookup_density=12.1,
    )

    request = await _builder().build("hp01", evidence=evidence)

    assert request.preferred_genres == ("fantasy", "adventure")
    assert request.operational_band.minimum_lexile == 680
    assert request.operational_band.maximum_lexile == 840
    assert request.handoff.target_band == request.operational_band
    assert request.handoff.evidence is evidence
    assert request.handoff.current_book == request.reference_books[0]
    assert request.handoff.current_book.title_zh == "哈利·波特"
    assert request.handoff.current_book.author == "J. K. Rowling"
    assert request.handoff.current_book.difficulty == BookDifficulty(880, 940)
    assert request.handoff.current_book.progress == 0.5


@pytest.mark.asyncio
async def test_handoff_rejects_unknown_frontend_book_id():
    with pytest.raises(
        DifficultyHandoffBookNotFoundError,
        match="unknown corpus book",
    ):
        await _builder().build(
            "missing",
            evidence=ReadingDifficultyEvidence(
                observed_word_count=1,
                observed_chapter_count=1,
                lookup_density=1,
            ),
        )
