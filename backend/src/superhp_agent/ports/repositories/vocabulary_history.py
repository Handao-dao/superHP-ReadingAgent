"""Read-only access to stored vocabulary contexts for Agent comparison."""

from typing import Protocol, runtime_checkable

from superhp_agent.contracts import VocabularyEncounter


class VocabularyHistoryRepositoryError(RuntimeError):
    """Infrastructure-neutral failure raised by a history adapter."""


@runtime_checkable
class VocabularyHistoryRepository(Protocol):
    """Find recent exact-lexeme encounters inside a trusted unit set.

    Results are returned in chronological order even when ``limit`` selects
    only the most recent stored contexts.
    """

    def find_encounters(
        self,
        *,
        language_id: str,
        normalized_word: str,
        book_id: str,
        allowed_unit_ids: tuple[str, ...],
        limit: int,
    ) -> tuple[VocabularyEncounter, ...]: ...
