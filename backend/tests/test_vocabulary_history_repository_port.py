"""Contract test for the read-only vocabulary-history capability."""

from superhp_agent.contracts import VocabularyEncounter
from superhp_agent.ports import VocabularyHistoryRepository


class FakeVocabularyHistoryRepository:
    """Minimal adapter showing that application code needs no SQLite details."""

    def find_encounters(
        self,
        *,
        language_id: str,
        normalized_word: str,
        book_id: str,
        allowed_unit_ids: tuple[str, ...],
        limit: int,
    ) -> tuple[VocabularyEncounter, ...]:
        del language_id, normalized_word, book_id, allowed_unit_ids, limit
        return ()


def test_vocabulary_history_repository_is_a_structural_port():
    repository = FakeVocabularyHistoryRepository()

    assert isinstance(repository, VocabularyHistoryRepository)
    assert (
        repository.find_encounters(
            language_id="en",
            normalized_word="charge",
            book_id="book-1",
            allowed_unit_ids=("chapter-1",),
            limit=5,
        )
        == ()
    )
