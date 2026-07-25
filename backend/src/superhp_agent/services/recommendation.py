"""Deterministic candidate matching for book recommendation.

This Service owns strict filtering and ranking over the catalog Port. It does
not talk to an LLM, serialize an Agent tool response, broaden search criteria,
or access SQLite directly.
"""

from __future__ import annotations

from dataclasses import replace

from superhp_agent.contracts import (
    BookCandidate,
    BookCandidateMatch,
    BookCandidateMatchResult,
    BookEntryKind,
    BookSearchQuery,
)
from superhp_agent.ports import BookDifficultyCatalog

_CATALOG_SCAN_LIMIT = 100
_ENTRY_KIND_RANK = {
    BookEntryKind.BOOK: 0,
    BookEntryKind.SERIES: 1,
    BookEntryKind.COLLECTION: 2,
    BookEntryKind.UNKNOWN: 3,
}


class RecommendationCandidateService:
    """Return a small, ranked set of candidates satisfying one strict query."""

    def __init__(self, catalog: BookDifficultyCatalog):
        self.catalog = catalog

    async def match(
        self,
        query: BookSearchQuery,
    ) -> BookCandidateMatchResult:
        """Match without silently changing difficulty, genres, or entry kinds."""
        scan_query = replace(query, limit=_CATALOG_SCAN_LIMIT)
        catalog_candidates = await self.catalog.search_books(scan_query)
        requested_genres = {
            genre.strip().casefold() for genre in query.categories if genre.strip()
        }
        requested_kinds = set(query.entry_kinds)
        excluded_ids = set(query.excluded_ids)

        matches_by_id: dict[str, BookCandidateMatch] = {}
        for candidate in catalog_candidates:
            if candidate.catalog_id in matches_by_id:
                continue
            if not _satisfies_query(
                candidate,
                query=query,
                requested_genres=requested_genres,
                requested_kinds=requested_kinds,
                excluded_ids=excluded_ids,
            ):
                continue
            matched_genres = tuple(
                genre
                for genre in candidate.genres
                if genre.casefold() in requested_genres
            )
            matches_by_id[candidate.catalog_id] = BookCandidateMatch(
                candidate=candidate,
                matched_genres=matched_genres,
                difficulty_distance=_difficulty_distance(candidate, query),
            )

        ranked = sorted(matches_by_id.values(), key=_match_rank)
        return BookCandidateMatchResult(
            query=query,
            matches=tuple(ranked[: query.limit]),
        )


def _satisfies_query(
    candidate: BookCandidate,
    *,
    query: BookSearchQuery,
    requested_genres: set[str],
    requested_kinds: set[BookEntryKind],
    excluded_ids: set[str],
) -> bool:
    if candidate.catalog_id in excluded_ids:
        return False
    if (
        query.lexile_min is not None
        and candidate.difficulty.maximum_lexile < query.lexile_min
    ):
        return False
    if (
        query.lexile_max is not None
        and candidate.difficulty.minimum_lexile > query.lexile_max
    ):
        return False
    if requested_kinds and candidate.entry_kind not in requested_kinds:
        return False
    candidate_genres = {genre.casefold() for genre in candidate.genres}
    return not requested_genres or bool(requested_genres & candidate_genres)


def _difficulty_distance(
    candidate: BookCandidate,
    query: BookSearchQuery,
) -> int:
    """Measure candidate-center distance from the requested band center."""
    if query.lexile_min is None and query.lexile_max is None:
        return 0
    query_min = query.lexile_min if query.lexile_min is not None else query.lexile_max
    query_max = query.lexile_max if query.lexile_max is not None else query.lexile_min
    assert query_min is not None and query_max is not None
    query_center = (query_min + query_max) / 2
    candidate_center = (
        candidate.difficulty.minimum_lexile + candidate.difficulty.maximum_lexile
    ) / 2
    return round(abs(candidate_center - query_center))


def _match_rank(match: BookCandidateMatch) -> tuple[object, ...]:
    """Prefer more tag evidence, closer difficulty, then concrete books."""
    candidate = match.candidate
    return (
        -len(match.matched_genres),
        match.difficulty_distance,
        _ENTRY_KIND_RANK[candidate.entry_kind],
        candidate.title_en.casefold(),
        candidate.catalog_id,
    )
