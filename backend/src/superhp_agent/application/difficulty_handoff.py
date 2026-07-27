"""Build a trusted recommendation handoff from persisted reading state.

The frontend only identifies the current book. This Application component
joins Corpus metadata, library grouping, reading progress, the local
difficulty catalog, and already-persisted difficulty evidence into the
structured context consumed by the recommendation Agent.
"""

from __future__ import annotations

from superhp_agent.contracts import (
    BookCandidate,
    BookDifficulty,
    BookRecommendationHandoff,
    BookSearchQuery,
    BookSnapshot,
    OperationalReadingBand,
    ReadingDifficultyEvidence,
    RecommendationOrigin,
    RecommendationRequest,
)
from superhp_agent.corpus import CorpusStore
from superhp_agent.library_catalog import LibraryCatalogStore
from superhp_agent.ports import BookDifficultyCatalog
from superhp_agent.ports.repositories import ReadingProgressRepository


class DifficultyHandoffBookNotFoundError(ValueError):
    """Raised when a frontend book id is not present in the local Corpus."""


class DifficultyRecommendationHandoffBuilder:
    """Assemble one difficulty-triggered recommendation request."""

    def __init__(
        self,
        corpus: CorpusStore,
        library_catalog: LibraryCatalogStore,
        difficulty_catalog: BookDifficultyCatalog,
        progress_repository: ReadingProgressRepository,
    ):
        self.corpus = corpus
        self.library_catalog = library_catalog
        self.difficulty_catalog = difficulty_catalog
        self.progress_repository = progress_repository

    async def build(
        self,
        book_id: str,
        *,
        evidence: ReadingDifficultyEvidence,
        preserve_genre_by_default: bool = True,
    ) -> RecommendationRequest:
        """Build from server-owned facts rather than frontend-supplied metadata."""
        normalized_book_id = str(book_id or "").strip()
        units = [
            unit
            for unit in self.corpus.list_units()
            if unit.book_id == normalized_book_id
        ]
        if not units:
            raise DifficultyHandoffBookNotFoundError(
                f"unknown corpus book: {normalized_book_id}"
            )

        collection = self.library_catalog.collection_for_book(
            normalized_book_id
        )
        candidate = await self._find_catalog_candidate(
            title=units[0].book_title,
            collection_id=collection.id if collection is not None else "",
            collection_title=collection.title if collection is not None else "",
        )
        genres = candidate.genres if candidate is not None else ()
        difficulty = candidate.difficulty if candidate is not None else None
        current_book = BookSnapshot(
            book_id=normalized_book_id,
            title=units[0].book_title,
            title_zh=candidate.title_zh if candidate is not None else "",
            author=(
                candidate.author
                if candidate is not None and candidate.author
                else collection.author if collection is not None else ""
            ),
            difficulty=difficulty,
            genres=genres,
            progress=self._book_progress(units),
        )
        target_band = _lower_target_band(difficulty)
        return RecommendationRequest(
            origin=RecommendationOrigin.DIFFICULTY_ALERT,
            preferred_genres=(
                genres if preserve_genre_by_default else ()
            ),
            operational_band=target_band,
            reference_books=(current_book,),
            handoff=BookRecommendationHandoff(
                current_book=current_book,
                evidence=evidence,
                target_band=target_band,
                preserve_genre_by_default=preserve_genre_by_default,
            ),
        )

    async def _find_catalog_candidate(
        self,
        *,
        title: str,
        collection_id: str,
        collection_title: str,
    ) -> BookCandidate | None:
        if collection_id:
            candidate = await self.difficulty_catalog.find_by_id(collection_id)
            if candidate is not None:
                return candidate

        expected_titles = {
            value.strip().casefold()
            for value in (title, collection_title)
            if value.strip()
        }
        if not expected_titles:
            return None
        candidates = await self.difficulty_catalog.search_books(
            BookSearchQuery(limit=100)
        )
        return next(
            (
                candidate
                for candidate in candidates
                if candidate.title_en.strip().casefold() in expected_titles
            ),
            None,
        )

    def _book_progress(self, units) -> float:
        read_ids = set(self.progress_repository.load().read_unit_ids)
        return len([unit for unit in units if unit.id in read_ids]) / len(units)


def _lower_target_band(
    difficulty: BookDifficulty | None,
) -> OperationalReadingBand | None:
    """Aim roughly 100–200L below the current title after sustained difficulty."""
    if difficulty is None:
        return None
    return OperationalReadingBand(
        minimum_lexile=max(0, difficulty.minimum_lexile - 200),
        maximum_lexile=max(0, difficulty.maximum_lexile - 100),
        confidence=0.7,
        evidence_source="difficulty_alert_three_chapter_window",
    )
