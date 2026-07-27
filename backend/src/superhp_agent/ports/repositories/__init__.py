"""Repository capabilities consumed by application and runtime layers."""

from superhp_agent.ports.repositories.bookmarks import BookmarkRepository
from superhp_agent.ports.repositories.reading_lookups import ReadingLookupRepository
from superhp_agent.ports.repositories.reading_progress import ReadingProgressRepository
from superhp_agent.ports.repositories.recommendation_sessions import (
    RecommendationSessionRepository,
)
from superhp_agent.ports.repositories.vocabulary import VocabularyRepository

__all__ = [
    "BookmarkRepository",
    "ReadingLookupRepository",
    "ReadingProgressRepository",
    "RecommendationSessionRepository",
    "VocabularyRepository",
]
