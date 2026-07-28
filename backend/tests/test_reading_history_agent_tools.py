"""Tests for model-facing tools backed by trusted prior-reading scope."""

import json

import pytest

from superhp_agent.agent_tools import (
    PreviousChapterSearchTool,
    ToolRegistry,
    VocabularyHistorySearchTool,
)
from superhp_agent.application import (
    PreviousChapterSearchError,
    VocabularyHistorySearchError,
)
from superhp_agent.contracts import (
    AgentToolExecutionContext,
    CompletedChapterScope,
    PreviousChapterExcerpt,
    PreviousChapterMatch,
    PreviousChapterSearchResult,
    PreviousReadingScope,
    VocabularyEncounter,
    VocabularyHistorySearchResult,
)


class FakePreviousChapterSearchService:
    def __init__(self, *, error=None):
        self.error = error
        self.requests = []

    def search(self, request):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return PreviousChapterSearchResult(
            request=request,
            matches=(
                PreviousChapterMatch(
                    chapter_id="book-1-ch01",
                    chapter_no=1,
                    chapter_title="Chapter One",
                    summary="Snape appeared at the feast.",
                    excerpts=(
                        PreviousChapterExcerpt(
                            unit_id="book-1-ch1",
                            text="Professor Snape looked across the hall.",
                        ),
                    ),
                ),
            ),
        )


class FakeVocabularyHistorySearchService:
    def __init__(self, *, error=None):
        self.error = error
        self.requests = []

    def search(self, request):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return VocabularyHistorySearchResult(
            request=request,
            normalized_word="charge",
            encounters=(
                VocabularyEncounter(
                    book_id="book-1",
                    chapter_id="book-1-ch01",
                    chapter_no=1,
                    unit_id="book-1-ch1",
                    word="charge",
                    normalized_word="charge",
                    translation="收费",
                    context="The hotel charged ten pounds.",
                    pos="verb",
                    mastered=True,
                ),
            ),
        )


def _context(*, with_history: bool = True) -> AgentToolExecutionContext:
    chapters = (
        (
            CompletedChapterScope(
                chapter_id="book-1-ch01",
                chapter_no=1,
                unit_ids=("book-1-ch1",),
            ),
        )
        if with_history
        else ()
    )
    return AgentToolExecutionContext(
        session_id="session-1",
        episode_id="episode-1",
        language_id="en",
        previous_reading_scope=PreviousReadingScope(
            book_id="book-1",
            current_chapter_id="book-1-ch02",
            current_chapter_no=2,
            completed_chapters=chapters,
        ),
    )


@pytest.mark.asyncio
async def test_previous_chapter_tool_uses_injected_scope_and_serializes_evidence():
    service = FakePreviousChapterSearchService()
    tool = PreviousChapterSearchTool(service)
    registry = ToolRegistry((tool,))

    result = await registry.execute(
        tool.name,
        {"query": "Snape", "max_chapters": 3},
        allowed_tools=(tool.name,),
        context=_context(),
    )

    request = service.requests[0]
    assert request.scope.book_id == "book-1"
    assert request.max_chapters == 3
    assert result["ok"] is True
    assert result["matches"][0]["chapter_no"] == 1
    assert result["matches"][0]["excerpts"][0]["unit_id"] == "book-1-ch1"
    assert json.loads(json.dumps(result, ensure_ascii=False)) == result
    assert set(tool.input_schema["properties"]) == {"query", "max_chapters"}


@pytest.mark.asyncio
async def test_vocabulary_tool_uses_trusted_language_and_scope():
    service = FakeVocabularyHistorySearchService()
    tool = VocabularyHistorySearchTool(service)

    result = await tool.run(
        context=_context(),
        word="Charge",
        max_encounters=3,
    )

    request = service.requests[0]
    assert request.language_id == "en"
    assert request.scope.book_id == "book-1"
    assert result["ok"] is True
    assert result["normalized_word"] == "charge"
    assert result["encounters"][0]["translation"] == "收费"
    assert result["encounters"][0]["mastered"] is True
    assert set(tool.input_schema["properties"]) == {
        "word",
        "max_encounters",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("context", "error"),
    [
        (None, "no_active_reading"),
        (_context(with_history=False), "no_completed_history"),
    ],
)
async def test_reading_history_tools_return_recoverable_context_errors(
    context,
    error,
):
    tool = PreviousChapterSearchTool(FakePreviousChapterSearchService())

    result = await tool.run(context=context, query="Snape")

    assert result == {
        "tool": "search_previous_chapters",
        "ok": False,
        "found": False,
        "error": error,
        "matches": [],
    }


@pytest.mark.asyncio
async def test_reading_history_tools_preserve_stable_service_errors():
    chapter_tool = PreviousChapterSearchTool(
        FakePreviousChapterSearchService(
            error=PreviousChapterSearchError(
                "scope_stale",
                "internal detail",
            )
        )
    )
    vocabulary_tool = VocabularyHistorySearchTool(
        FakeVocabularyHistorySearchService(
            error=VocabularyHistorySearchError(
                "vocabulary_history_unavailable",
                "internal detail",
            )
        )
    )

    chapter_result = await chapter_tool.run(
        context=_context(),
        query="Snape",
    )
    vocabulary_result = await vocabulary_tool.run(
        context=_context(),
        word="charge",
    )

    assert chapter_result["error"] == "scope_stale"
    assert "internal detail" not in json.dumps(chapter_result)
    assert vocabulary_result["error"] == "vocabulary_history_unavailable"
    assert "internal detail" not in json.dumps(vocabulary_result)


@pytest.mark.asyncio
async def test_reading_history_tools_reject_non_json_schema_argument_types():
    chapter_tool = PreviousChapterSearchTool(
        FakePreviousChapterSearchService()
    )
    vocabulary_tool = VocabularyHistorySearchTool(
        FakeVocabularyHistorySearchService()
    )

    with pytest.raises(TypeError, match="query must be a string"):
        await chapter_tool.run(context=_context(), query=123)
    with pytest.raises(TypeError, match="must be an integer"):
        await vocabulary_tool.run(
            context=_context(),
            word="charge",
            max_encounters=True,
        )
