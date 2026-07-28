"""Retrieve stored uses of one exact word from completed prior chapters.

The service normalizes a query, delegates bounded storage access, and wraps
typed encounters in the companion Contract. It does not perform dictionary
lookup, lemmatization, semantic comparison, or Agent response generation.
"""

from __future__ import annotations

from superhp_agent.contracts import (
    VocabularyHistorySearchRequest,
    VocabularyHistorySearchResult,
)
from superhp_agent.domain.vocabulary import normalize_word
from superhp_agent.ports.repositories import (
    VocabularyHistoryRepository,
    VocabularyHistoryRepositoryError,
)


class VocabularyHistorySearchError(RuntimeError):
    """Stable application error that a future Tool can map to JSON."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class VocabularyHistorySearchService:
    """Find recent stored contexts inside the request's trusted scope."""

    def __init__(self, repository: VocabularyHistoryRepository):
        self.repository = repository

    def search(
        self,
        request: VocabularyHistorySearchRequest,
    ) -> VocabularyHistorySearchResult:
        """Return exact-lexeme contexts, newest budget first then chronological."""
        normalized_word = normalize_word(request.word)
        if not normalized_word:
            raise ValueError("word must contain a searchable value")

        allowed_unit_ids = request.scope.searchable_unit_ids
        if not allowed_unit_ids:
            return VocabularyHistorySearchResult(
                request=request,
                normalized_word=normalized_word,
            )

        try:
            encounters = self.repository.find_encounters(
                language_id=request.language_id,
                normalized_word=normalized_word,
                book_id=request.scope.book_id,
                allowed_unit_ids=allowed_unit_ids,
                limit=request.max_encounters + 1,
            )
        except VocabularyHistoryRepositoryError as exc:
            raise VocabularyHistorySearchError(
                "vocabulary_history_unavailable",
                "The stored vocabulary history is unavailable.",
            ) from exc

        truncated = len(encounters) > request.max_encounters
        if truncated:
            encounters = encounters[-request.max_encounters :]
        return VocabularyHistorySearchResult(
            request=request,
            normalized_word=normalized_word,
            encounters=encounters,
            truncated=truncated,
        )
