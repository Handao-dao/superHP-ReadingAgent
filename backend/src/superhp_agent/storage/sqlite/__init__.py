"""SQLite implementations of repository capabilities."""

from superhp_agent.storage.sqlite.bookmarks import SQLiteBookmarkRepository
from superhp_agent.storage.sqlite.chapter_checkpoints import (
    SQLiteChapterReadingCheckpointRepository,
)
from superhp_agent.storage.sqlite.conversation_memories import (
    SQLiteConversationMemoryRepository,
)
from superhp_agent.storage.sqlite.reading_companion import (
    SQLiteReadingCompanionRepository,
)
from superhp_agent.storage.sqlite.reading_difficulty_prompts import (
    SQLiteReadingDifficultyPromptRepository,
)
from superhp_agent.storage.sqlite.reading_lookups import SQLiteReadingLookupRepository
from superhp_agent.storage.sqlite.reading_progress import (
    SQLiteReadingProgressRepository,
)
from superhp_agent.storage.sqlite.reading_support import (
    SQLiteReadingSupportRepository,
)
from superhp_agent.storage.sqlite.recommendation_catalog import (
    SQLiteBookDifficultyCatalog,
)
from superhp_agent.storage.sqlite.recommendation_sessions import (
    SQLiteRecommendationSessionRepository,
)
from superhp_agent.storage.sqlite.units import SQLiteUnitRepository
from superhp_agent.storage.sqlite.vocabulary import SQLiteVocabularyRepository
from superhp_agent.storage.sqlite.vocabulary_history import (
    SQLiteVocabularyHistoryRepository,
)

__all__ = [
    "SQLiteBookmarkRepository",
    "SQLiteChapterReadingCheckpointRepository",
    "SQLiteConversationMemoryRepository",
    "SQLiteReadingProgressRepository",
    "SQLiteReadingCompanionRepository",
    "SQLiteReadingLookupRepository",
    "SQLiteReadingDifficultyPromptRepository",
    "SQLiteReadingSupportRepository",
    "SQLiteBookDifficultyCatalog",
    "SQLiteRecommendationSessionRepository",
    "SQLiteUnitRepository",
    "SQLiteVocabularyRepository",
    "SQLiteVocabularyHistoryRepository",
]
