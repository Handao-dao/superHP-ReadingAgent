"""Capability interfaces used by backend application and service layers."""

from superhp_agent.ports.book_catalog import BookDifficultyCatalog
from superhp_agent.ports.events import (
    EventLogger,
    EventSink,
    emit_backend_event,
)
from superhp_agent.ports.llm import LLMProvider
from superhp_agent.ports.repositories import (
    BookmarkRepository,
    ChapterReadingCheckpointRepository,
    ReadingDifficultyPromptRepository,
    ReadingLookupRepository,
    ReadingSupportRepository,
    RecommendationSessionRepository,
    VocabularyHistoryRepository,
    VocabularyRepository,
)

__all__ = [
    "BookDifficultyCatalog",
    "BookmarkRepository",
    "ChapterReadingCheckpointRepository",
    "EventLogger",
    "EventSink",
    "LLMProvider",
    "ReadingLookupRepository",
    "ReadingDifficultyPromptRepository",
    "ReadingSupportRepository",
    "RecommendationSessionRepository",
    "VocabularyHistoryRepository",
    "VocabularyRepository",
    "emit_backend_event",
]
