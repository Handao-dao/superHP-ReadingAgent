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
    ReadingLookupRepository,
    ReadingSupportRepository,
    RecommendationSessionRepository,
    VocabularyRepository,
)

__all__ = [
    "BookDifficultyCatalog",
    "BookmarkRepository",
    "EventLogger",
    "EventSink",
    "LLMProvider",
    "ReadingLookupRepository",
    "ReadingSupportRepository",
    "RecommendationSessionRepository",
    "VocabularyRepository",
    "emit_backend_event",
]
