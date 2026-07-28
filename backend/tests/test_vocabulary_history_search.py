"""Application tests for exact vocabulary-history search."""

import pytest

from superhp_agent.application import (
    VocabularyHistorySearchError,
    VocabularyHistorySearchService,
)
from superhp_agent.contracts import (
    CompletedChapterScope,
    PreviousReadingScope,
    VocabularyEncounter,
    VocabularyHistorySearchRequest,
)
from superhp_agent.ports import VocabularyHistoryRepositoryError


class FakeVocabularyHistoryRepository:
    def __init__(self, encounters=(), *, error=None):
        self.encounters = tuple(encounters)
        self.error = error
        self.calls = []

    def find_encounters(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.encounters


def _scope(*chapter_numbers: int) -> PreviousReadingScope:
    return PreviousReadingScope(
        book_id="book-1",
        current_chapter_id="book-1-ch04",
        current_chapter_no=4,
        completed_chapters=tuple(
            CompletedChapterScope(
                chapter_id=f"book-1-ch{chapter_no:02d}",
                chapter_no=chapter_no,
                unit_ids=(f"book-1-ch{chapter_no}",),
            )
            for chapter_no in chapter_numbers
        ),
    )


def _encounter(chapter_no: int) -> VocabularyEncounter:
    return VocabularyEncounter(
        book_id="book-1",
        chapter_id=f"book-1-ch{chapter_no:02d}",
        chapter_no=chapter_no,
        unit_id=f"book-1-ch{chapter_no}",
        word="charge",
        normalized_word="charge",
        translation=f"meaning-{chapter_no}",
        context=f"Context from chapter {chapter_no}.",
    )


def test_service_normalizes_query_and_keeps_latest_context_budget():
    repository = FakeVocabularyHistoryRepository(
        tuple(_encounter(chapter_no) for chapter_no in (1, 2, 3))
    )
    request = VocabularyHistorySearchRequest(
        word=" Charge ",
        language_id="en",
        scope=_scope(1, 2, 3),
        max_encounters=2,
    )

    result = VocabularyHistorySearchService(repository).search(request)

    assert result.normalized_word == "charge"
    assert [item.chapter_no for item in result.encounters] == [2, 3]
    assert result.truncated is True
    assert repository.calls == [
        {
            "language_id": "en",
            "normalized_word": "charge",
            "book_id": "book-1",
            "allowed_unit_ids": (
                "book-1-ch1",
                "book-1-ch2",
                "book-1-ch3",
            ),
            "limit": 3,
        }
    ]


def test_service_returns_empty_without_querying_when_no_history_is_allowed():
    repository = FakeVocabularyHistoryRepository()
    request = VocabularyHistorySearchRequest(
        word="charge",
        language_id="en",
        scope=_scope(),
    )

    result = VocabularyHistorySearchService(repository).search(request)

    assert result.found is False
    assert result.truncated is False
    assert repository.calls == []


def test_service_normalizes_repository_failure_for_a_future_tool():
    repository = FakeVocabularyHistoryRepository(
        error=VocabularyHistoryRepositoryError("database unavailable")
    )

    with pytest.raises(VocabularyHistorySearchError) as captured:
        VocabularyHistorySearchService(repository).search(
            VocabularyHistorySearchRequest(
                word="charge",
                language_id="en",
                scope=_scope(1),
            )
        )

    assert captured.value.code == "vocabulary_history_unavailable"
