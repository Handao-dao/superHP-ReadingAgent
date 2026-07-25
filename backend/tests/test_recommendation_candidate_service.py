"""Tests for strict recommendation candidate matching and ranking."""

import pytest

from superhp_agent.contracts import (
    BookCandidate,
    BookDifficulty,
    BookEntryKind,
    BookSearchQuery,
)
from superhp_agent.services import RecommendationCandidateService


class RecordingCatalog:
    """Small Port test double that records the Service's scan query."""

    def __init__(self, candidates):
        self.candidates = candidates
        self.queries = []

    async def find_by_id(self, catalog_id: str):
        return next(
            (
                candidate
                for candidate in self.candidates
                if candidate.catalog_id == catalog_id
            ),
            None,
        )

    async def search_books(self, query: BookSearchQuery):
        self.queries.append(query)
        return list(self.candidates)


def candidate(
    catalog_id: str,
    lexile: int,
    *genres: str,
    kind: BookEntryKind = BookEntryKind.BOOK,
) -> BookCandidate:
    return BookCandidate(
        catalog_id=catalog_id,
        title_en=catalog_id.replace("-", " ").title(),
        difficulty=BookDifficulty(lexile, lexile),
        entry_kind=kind,
        genres=genres,
    )


@pytest.mark.asyncio
async def test_service_strictly_filters_deduplicates_and_ranks_candidates():
    strong = candidate("strong", 760, "mystery", "school_life")
    close = candidate("close", 750, "mystery")
    series = candidate(
        "series",
        750,
        "mystery",
        kind=BookEntryKind.SERIES,
    )
    excluded = candidate("excluded", 755, "mystery", "school_life")
    wrong_genre = candidate("fantasy", 750, "fantasy")
    too_hard = candidate("too-hard", 900, "mystery")
    catalog = RecordingCatalog(
        [
            close,
            wrong_genre,
            strong,
            strong,
            too_hard,
            excluded,
            series,
        ]
    )
    service = RecommendationCandidateService(catalog)
    query = BookSearchQuery(
        lexile_min=700,
        lexile_max=800,
        categories=("mystery", "school_life"),
        excluded_ids=("excluded",),
        limit=3,
    )

    result = await service.match(query)

    assert result.found is True
    assert [match.candidate.catalog_id for match in result.matches] == [
        "strong",
        "close",
        "series",
    ]
    assert result.matches[0].matched_genres == ("mystery", "school_life")
    assert result.matches[0].difficulty_distance == 10
    assert catalog.queries[0].limit == 100
    assert result.query is query


@pytest.mark.asyncio
async def test_service_respects_requested_entry_kinds_and_output_limit():
    catalog = RecordingCatalog(
        [
            candidate("book", 600, "fantasy"),
            candidate(
                "series-b",
                610,
                "fantasy",
                kind=BookEntryKind.SERIES,
            ),
            candidate(
                "series-a",
                590,
                "fantasy",
                kind=BookEntryKind.SERIES,
            ),
        ]
    )
    service = RecommendationCandidateService(catalog)

    result = await service.match(
        BookSearchQuery(
            lexile_min=500,
            lexile_max=700,
            categories=("fantasy",),
            entry_kinds=(BookEntryKind.SERIES,),
            limit=1,
        )
    )

    assert len(result.matches) == 1
    assert result.matches[0].candidate.catalog_id == "series-a"


@pytest.mark.asyncio
async def test_service_returns_explicit_empty_strict_result():
    service = RecommendationCandidateService(
        RecordingCatalog([candidate("fantasy", 900, "fantasy")])
    )
    query = BookSearchQuery(
        lexile_min=400,
        lexile_max=500,
        categories=("mystery",),
    )

    result = await service.match(query)

    assert result.found is False
    assert result.matches == ()
