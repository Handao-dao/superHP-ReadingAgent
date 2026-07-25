"""Read-only local-catalog tool for a future recommendation Agent.

The wrapper accepts JSON-friendly primitives and delegates all filtering and
ranking to RecommendationCandidateService. It is deliberately independent of
any particular Agent SDK so registration can be added without moving business
rules into model-facing code.
"""

from __future__ import annotations

from collections.abc import Iterable

from superhp_agent.contracts import (
    BookCandidateMatch,
    BookEntryKind,
    BookSearchQuery,
)
from superhp_agent.services.recommendation import RecommendationCandidateService


class BookCatalogSearchTool:
    """Expose strict local-book matching through one read-only tool call."""

    name = "search_local_book_catalog"
    description = (
        "Search locally available English books by Lexile range and style tags. "
        "Returns strict matches only and never widens the requested criteria."
    )

    def __init__(self, service: RecommendationCandidateService):
        self.service = service

    async def run(
        self,
        *,
        lexile_min: int | None = None,
        lexile_max: int | None = None,
        genres: Iterable[str] = (),
        entry_kinds: Iterable[str] = (),
        excluded_ids: Iterable[str] = (),
        limit: int = 5,
    ) -> dict[str, object]:
        """Search with model-friendly values and return a JSON-ready result."""
        normalized_genres = _normalize_values(genres)
        if lexile_min is None and lexile_max is None and not normalized_genres:
            raise ValueError("at least one Lexile bound or genre is required")

        query = BookSearchQuery(
            lexile_min=lexile_min,
            lexile_max=lexile_max,
            categories=normalized_genres,
            entry_kinds=_parse_entry_kinds(entry_kinds),
            excluded_ids=_normalize_values(excluded_ids),
            limit=limit,
        )
        result = await self.service.match(query)
        return {
            "tool": self.name,
            "match_mode": "strict",
            "criteria": {
                "lexile_min": query.lexile_min,
                "lexile_max": query.lexile_max,
                "genres": list(query.categories),
                "entry_kinds": [kind.value for kind in query.entry_kinds],
                "excluded_ids": list(query.excluded_ids),
                "limit": query.limit,
            },
            "found": result.found,
            "result_count": len(result.matches),
            "candidates": [
                _serialize_match(rank, match)
                for rank, match in enumerate(result.matches, start=1)
            ],
        }


def _normalize_values(values: Iterable[str]) -> tuple[str, ...]:
    """Strip, case-fold, de-duplicate, and preserve first-seen order."""
    if isinstance(values, str):
        values = (values,)
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean_value = value.strip().casefold()
        if not clean_value or clean_value in seen:
            continue
        seen.add(clean_value)
        normalized.append(clean_value)
    return tuple(normalized)


def _parse_entry_kinds(values: Iterable[str]) -> tuple[BookEntryKind, ...]:
    parsed: list[BookEntryKind] = []
    for value in _normalize_values(values):
        try:
            parsed.append(BookEntryKind(value))
        except ValueError as exc:
            allowed = ", ".join(kind.value for kind in BookEntryKind)
            raise ValueError(
                f"unknown entry kind {value!r}; expected one of: {allowed}"
            ) from exc
    return tuple(parsed)


def _serialize_match(
    rank: int,
    match: BookCandidateMatch,
) -> dict[str, object]:
    candidate = match.candidate
    return {
        "rank": rank,
        "catalog_id": candidate.catalog_id,
        "title_en": candidate.title_en,
        "title_zh": candidate.title_zh,
        "author": candidate.author,
        "entry_kind": candidate.entry_kind.value,
        "lexile_min": candidate.difficulty.minimum_lexile,
        "lexile_max": candidate.difficulty.maximum_lexile,
        "genres": list(candidate.genres),
        "matched_genres": list(match.matched_genres),
        "difficulty_distance": match.difficulty_distance,
    }
