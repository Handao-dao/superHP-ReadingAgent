"""Repository capabilities consumed by application and runtime layers."""

from superhp_agent.ports.repositories.bookmarks import BookmarkRepository
from superhp_agent.ports.repositories.chapter_checkpoints import (
    ChapterReadingCheckpointRepository,
)
from superhp_agent.ports.repositories.conversation_memories import (
    ConversationMemoryRepository,
)
from superhp_agent.ports.repositories.reading_companion import (
    ReadingCompanionRepository,
)
from superhp_agent.ports.repositories.reading_difficulty_prompts import (
    ReadingDifficultyPromptRepository,
)
from superhp_agent.ports.repositories.reading_lookups import ReadingLookupRepository
from superhp_agent.ports.repositories.reading_progress import ReadingProgressRepository
from superhp_agent.ports.repositories.reading_support import ReadingSupportRepository
from superhp_agent.ports.repositories.recommendation_sessions import (
    RecommendationSessionRepository,
)
from superhp_agent.ports.repositories.vocabulary import VocabularyRepository
from superhp_agent.ports.repositories.vocabulary_history import (
    VocabularyHistoryRepository,
    VocabularyHistoryRepositoryError,
)

__all__ = [
    "BookmarkRepository",
    "ConversationMemoryRepository",
    "ChapterReadingCheckpointRepository",
    "ReadingLookupRepository",
    "ReadingDifficultyPromptRepository",
    "ReadingProgressRepository",
    "ReadingCompanionRepository",
    "ReadingSupportRepository",
    "RecommendationSessionRepository",
    "VocabularyRepository",
    "VocabularyHistoryRepository",
    "VocabularyHistoryRepositoryError",
]
