"""Model-facing tools for evidence from completed previous chapters.

These adapters expose only narrow JSON arguments. Book, language, chapter, and
unit access are injected through ``AgentToolExecutionContext`` and can never
be widened by model-generated arguments.
"""

from __future__ import annotations

from superhp_agent.application.previous_chapter_search import (
    PreviousChapterSearchError,
    PreviousChapterSearchService,
)
from superhp_agent.application.vocabulary_history_search import (
    VocabularyHistorySearchError,
    VocabularyHistorySearchService,
)
from superhp_agent.contracts import (
    AgentToolExecutionContext,
    PreviousChapterSearchRequest,
    PreviousReadingScope,
    VocabularyHistorySearchRequest,
)


class PreviousChapterSearchTool:
    """Expose prior chapter evidence without exposing scope controls."""

    name = "search_previous_chapters"
    description = (
        "Search people, events, or plot details only in chapters the reader "
        "fully completed before the current chapter. Use a short name or "
        "event phrase, not a full conversational question."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 1},
            "max_chapters": {
                "type": "integer",
                "minimum": 1,
                "maximum": 10,
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    def __init__(self, service: PreviousChapterSearchService):
        self.service = service

    async def run(
        self,
        *,
        context: AgentToolExecutionContext | None = None,
        query: str,
        max_chapters: int = 4,
    ) -> dict[str, object]:
        """Search with trusted scope supplied outside model arguments."""
        _validate_text(query, "query")
        _validate_limit(max_chapters, "max_chapters")
        scope_or_error = _require_previous_scope(self.name, context, "matches")
        if isinstance(scope_or_error, dict):
            return scope_or_error
        try:
            result = self.service.search(
                PreviousChapterSearchRequest(
                    query=query,
                    scope=scope_or_error,
                    max_chapters=max_chapters,
                )
            )
        except PreviousChapterSearchError as exc:
            return _error_result(self.name, exc.code, "matches")

        return {
            "tool": self.name,
            "ok": True,
            "found": result.found,
            "query": result.request.query.strip(),
            "result_count": len(result.matches),
            "truncated": result.truncated,
            "matches": [
                {
                    "chapter_id": match.chapter_id,
                    "chapter_no": match.chapter_no,
                    "chapter_title": match.chapter_title,
                    "summary": match.summary,
                    "excerpts": [
                        {
                            "unit_id": excerpt.unit_id,
                            "text": excerpt.text,
                        }
                        for excerpt in match.excerpts
                    ],
                }
                for match in result.matches
            ],
        }


class VocabularyHistorySearchTool:
    """Expose stored same-word contexts from completed prior chapters."""

    name = "search_vocabulary_history"
    description = (
        "Find earlier stored contexts for one exact word in this book's "
        "fully completed previous chapters. Use it to compare prior meanings "
        "or usage; it is not a general dictionary lookup."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "word": {"type": "string", "minLength": 1},
            "max_encounters": {
                "type": "integer",
                "minimum": 1,
                "maximum": 10,
            },
        },
        "required": ["word"],
        "additionalProperties": False,
    }

    def __init__(self, service: VocabularyHistorySearchService):
        self.service = service

    async def run(
        self,
        *,
        context: AgentToolExecutionContext | None = None,
        word: str,
        max_encounters: int = 5,
    ) -> dict[str, object]:
        """Search exact stored contexts using trusted book and language."""
        _validate_text(word, "word")
        _validate_limit(max_encounters, "max_encounters")
        scope_or_error = _require_previous_scope(
            self.name,
            context,
            "encounters",
        )
        if isinstance(scope_or_error, dict):
            return scope_or_error
        assert context is not None
        try:
            result = self.service.search(
                VocabularyHistorySearchRequest(
                    word=word,
                    language_id=context.language_id,
                    scope=scope_or_error,
                    max_encounters=max_encounters,
                )
            )
        except VocabularyHistorySearchError as exc:
            return _error_result(self.name, exc.code, "encounters")

        return {
            "tool": self.name,
            "ok": True,
            "found": result.found,
            "word": result.request.word.strip(),
            "normalized_word": result.normalized_word,
            "result_count": len(result.encounters),
            "truncated": result.truncated,
            "encounters": [
                {
                    "chapter_id": encounter.chapter_id,
                    "chapter_no": encounter.chapter_no,
                    "unit_id": encounter.unit_id,
                    "word": encounter.word,
                    "translation": encounter.translation,
                    "context": encounter.context,
                    "pos": encounter.pos,
                    "encounter_count": encounter.encounter_count,
                    "mastered": encounter.mastered,
                }
                for encounter in result.encounters
            ],
        }


def _require_previous_scope(
    tool_name: str,
    context: AgentToolExecutionContext | None,
    result_key: str,
) -> PreviousReadingScope | dict[str, object]:
    """Return trusted scope or a stable recoverable Tool result."""
    if context is None or context.previous_reading_scope is None:
        return _error_result(tool_name, "no_active_reading", result_key)
    if not context.previous_reading_scope.completed_chapters:
        return _error_result(tool_name, "no_completed_history", result_key)
    return context.previous_reading_scope


def _error_result(
    tool_name: str,
    error: str,
    result_key: str,
) -> dict[str, object]:
    return {
        "tool": tool_name,
        "ok": False,
        "found": False,
        "error": error,
        result_key: [],
    }


def _validate_limit(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")


def _validate_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
