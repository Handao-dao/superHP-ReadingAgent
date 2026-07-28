"""Tests for spoiler-safe search across completed previous chapters."""

from pathlib import Path

import pytest

from superhp_agent.application import (
    PreviousChapterSearchError,
    PreviousChapterSearchPolicy,
    PreviousChapterSearchService,
)
from superhp_agent.contracts import (
    CompletedChapterScope,
    PreviousChapterSearchRequest,
    PreviousReadingScope,
)
from superhp_agent.corpus import CorpusError, ReadingUnit, ReadingUnitDocument


class FakeCorpus:
    def __init__(self, documents):
        self.documents = {
            document.meta.id: document for document in documents
        }
        self.opened_unit_ids = []

    def list_units(self):
        return [
            document.meta for document in self.documents.values()
        ]

    def get_unit(self, unit_id):
        self.opened_unit_ids.append(unit_id)
        return self.documents[unit_id]


class BrokenCorpus:
    def list_units(self):
        raise CorpusError("broken corpus")


def _document(
    *,
    unit_id: str,
    chapter_no: int,
    body: str,
    summary: str = "",
    chapter_id: str | None = None,
    book_id: str = "book-1",
    section_no: int = 1,
) -> ReadingUnitDocument:
    chapter_id = chapter_id or f"{book_id}-ch{chapter_no:02d}"
    return ReadingUnitDocument(
        meta=ReadingUnit(
            id=unit_id,
            chapter_id=chapter_id,
            book_id=book_id,
            book_title="Book One",
            chapter_no=chapter_no,
            chapter_title=f"Chapter {chapter_no}",
            section_no=section_no,
            section_count=1,
            summary=summary,
            path=Path(f"{unit_id}.md"),
        ),
        body=body,
    )


def _scope(
    *chapters: tuple[int, tuple[str, ...]],
) -> PreviousReadingScope:
    return PreviousReadingScope(
        book_id="book-1",
        current_chapter_id="book-1-ch04",
        current_chapter_no=4,
        completed_chapters=tuple(
            CompletedChapterScope(
                chapter_id=f"book-1-ch{chapter_no:02d}",
                chapter_no=chapter_no,
                unit_ids=unit_ids,
            )
            for chapter_no, unit_ids in chapters
        ),
    )


def test_search_groups_summary_and_source_without_opening_current_chapter():
    corpus = FakeCorpus(
        (
            _document(
                unit_id="ch1",
                chapter_no=1,
                summary="Harry first notices Professor Snape at the feast.",
                body=(
                    "The students entered the hall.\n\n"
                    "Professor Snape looked directly at Harry."
                ),
            ),
            _document(
                unit_id="ch2",
                chapter_no=2,
                summary="The class begins.",
                body="Snape questioned Harry during the lesson.",
            ),
            _document(
                unit_id="ch4-current",
                chapter_no=4,
                body="Current chapter content about Snape must stay closed.",
            ),
        )
    )
    request = PreviousChapterSearchRequest(
        query="Snape",
        scope=_scope((1, ("ch1",)), (2, ("ch2",))),
    )

    result = PreviousChapterSearchService(corpus).search(request)

    assert result.found is True
    assert [match.chapter_no for match in result.matches] == [1, 2]
    assert result.matches[0].summary.startswith("Harry")
    assert result.matches[0].excerpts[0].unit_id == "ch1"
    assert corpus.opened_unit_ids == ["ch1", "ch2"]
    assert "ch4-current" not in corpus.opened_unit_ids


def test_search_selects_by_relevance_then_returns_chronologically():
    corpus = FakeCorpus(
        (
            _document(
                unit_id="ch1",
                chapter_no=1,
                body="Holmes noticed the letter.",
            ),
            _document(
                unit_id="ch2",
                chapter_no=2,
                body="Holmes waited.",
            ),
            _document(
                unit_id="ch3",
                chapter_no=3,
                body="Holmes questioned Holmes and then followed Holmes.",
            ),
        )
    )
    request = PreviousChapterSearchRequest(
        query="Holmes",
        scope=_scope(
            (1, ("ch1",)),
            (2, ("ch2",)),
            (3, ("ch3",)),
        ),
        max_chapters=2,
    )

    result = PreviousChapterSearchService(corpus).search(request)

    assert [match.chapter_no for match in result.matches] == [2, 3]
    assert result.truncated is True


def test_search_returns_multiple_bounded_excerpts_from_the_same_unit():
    long_paragraph = f"{'before ' * 30}clue{' after' * 30}"
    corpus = FakeCorpus(
        (
            _document(
                unit_id="ch1",
                chapter_no=1,
                body=(
                    f"{long_paragraph}\n\n"
                    "A second clue appeared beside the door.\n\n"
                    "A third clue was hidden under the rug."
                ),
            ),
        )
    )
    service = PreviousChapterSearchService(
        corpus,
        policy=PreviousChapterSearchPolicy(
            max_excerpts_per_chapter=2,
            max_excerpt_chars=100,
        ),
    )

    result = service.search(
        PreviousChapterSearchRequest(
            query="clue",
            scope=_scope((1, ("ch1",))),
        )
    )

    assert len(result.matches[0].excerpts) == 2
    assert all(
        excerpt.unit_id == "ch1"
        for excerpt in result.matches[0].excerpts
    )
    assert all(
        len(excerpt.text) <= 100
        for excerpt in result.matches[0].excerpts
    )
    assert result.truncated is True


def test_search_does_not_match_short_word_inside_a_longer_word():
    corpus = FakeCorpus(
        (
            _document(
                unit_id="ch1",
                chapter_no=1,
                body="The theatre was empty.",
            ),
        )
    )

    result = PreviousChapterSearchService(corpus).search(
        PreviousChapterSearchRequest(
            query="he",
            scope=_scope((1, ("ch1",))),
        )
    )

    assert result.found is False
    assert result.truncated is False


def test_search_rejects_scope_that_no_longer_matches_corpus():
    corpus = FakeCorpus(
        (
            _document(
                unit_id="ch1",
                chapter_no=2,
                body="A clue.",
            ),
        )
    )

    with pytest.raises(PreviousChapterSearchError) as captured:
        PreviousChapterSearchService(corpus).search(
            PreviousChapterSearchRequest(
                query="clue",
                scope=_scope((1, ("ch1",))),
            )
        )

    assert captured.value.code == "scope_stale"


def test_search_normalizes_corpus_failures_for_a_future_tool():
    with pytest.raises(PreviousChapterSearchError) as captured:
        PreviousChapterSearchService(BrokenCorpus()).search(
            PreviousChapterSearchRequest(
                query="clue",
                scope=_scope((1, ("ch1",))),
            )
        )

    assert captured.value.code == "corpus_unavailable"
