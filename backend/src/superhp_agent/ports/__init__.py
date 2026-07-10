"""Capability interfaces used by backend application and service layers."""

from superhp_agent.ports.events import (
    EventEmitter,
    EventLogger,
    EventSink,
    emit_backend_event,
)
from superhp_agent.ports.llm import LLMProvider
from superhp_agent.ports.repositories import BookmarkRepository, VocabularyRepository

__all__ = [
    "BookmarkRepository",
    "EventEmitter",
    "EventLogger",
    "EventSink",
    "LLMProvider",
    "VocabularyRepository",
    "emit_backend_event",
]
