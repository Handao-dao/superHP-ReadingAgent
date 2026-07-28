"""Read-only access to stored vocabulary contexts for Agent comparison."""

from typing import Protocol, runtime_checkable

from superhp_agent.contracts import VocabularyEncounter


@runtime_checkable
class VocabularyHistoryRepository(Protocol):
    """Find exact-lexeme encounters inside an explicit trusted unit set."""

    def find_encounters(
        self,
        *,
        language_id: str,
        normalized_word: str,
        book_id: str,
        allowed_unit_ids: tuple[str, ...],
        limit: int,
    ) -> tuple[VocabularyEncounter, ...]: ...
