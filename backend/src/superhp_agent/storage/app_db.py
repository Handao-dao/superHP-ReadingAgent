"""Composition facade for the application's SQLite repositories.

AppDB composes the shared connection, migrations, and concrete repository
implementations. It contains no repository SQL.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from superhp_agent.corpus import ReadingUnit
from superhp_agent.domain.reading_support import ReadingSupportState
from superhp_agent.storage.database import SQLiteDatabase
from superhp_agent.storage.migrations import initialize_schema
from superhp_agent.storage.sqlite.bookmarks import (
    SQLiteBookmarkRepository,
)
from superhp_agent.storage.sqlite.chapter_checkpoints import (
    SQLiteChapterReadingCheckpointRepository,
)
from superhp_agent.storage.sqlite.reading_difficulty_prompts import (
    SQLiteReadingDifficultyPromptRepository,
)
from superhp_agent.storage.sqlite.reading_lookups import (
    SQLiteReadingLookupRepository,
)
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
from superhp_agent.storage.sqlite.vocabulary import (
    SQLiteVocabularyRepository,
)
from superhp_agent.storage.sqlite.vocabulary_history import (
    SQLiteVocabularyHistoryRepository,
)


class AppDB:
    """Lifecycle facade that composes SQLite repository implementations."""

    def __init__(self, db_path: str | Path):
        self.database = SQLiteDatabase(db_path)
        self.path = self.database.path
        # Compatibility references while repository SQL remains in AppDB.
        self._conn = self.database.connection
        self._lock = self.database.lock
        initialize_schema(self._conn)
        self.unit_repository = SQLiteUnitRepository(self.database)
        self.vocabulary_repository = SQLiteVocabularyRepository(
            self.database,
            sync_unit=self.unit_repository.sync,
        )
        self.vocabulary_history_repository = (
            SQLiteVocabularyHistoryRepository(self.database)
        )
        self.bookmark_repository = SQLiteBookmarkRepository(
            self.database,
            sync_unit=self.unit_repository.sync,
        )
        self.reading_progress_repository = SQLiteReadingProgressRepository(self.database)
        self.reading_lookup_repository = SQLiteReadingLookupRepository(
            self.database,
            sync_unit=self.unit_repository.sync,
        )
        self.reading_difficulty_prompt_repository = (
            SQLiteReadingDifficultyPromptRepository(self.database)
        )
        self.reading_support_repository = SQLiteReadingSupportRepository(
            self.database
        )
        self.chapter_checkpoint_repository = (
            SQLiteChapterReadingCheckpointRepository(self.database)
        )
        self.book_difficulty_catalog = SQLiteBookDifficultyCatalog(self.database)
        self.recommendation_session_repository = (
            SQLiteRecommendationSessionRepository(self.database)
        )

    def close(self) -> None:
        self.database.close()

    def sync_unit(self, unit: ReadingUnit) -> None:
        self.unit_repository.sync(unit)

    def add_vocabulary_items(self, unit: ReadingUnit, items: list[Any]) -> int:
        return self.vocabulary_repository.add_vocabulary_items(unit, items)

    def add_manual_vocabulary(
        self,
        unit: ReadingUnit,
        *,
        word: str,
        translation: str,
        context: str = "",
        pos: str = "other",
    ) -> int:
        return self.vocabulary_repository.add_manual_vocabulary(
            unit,
            word=word,
            translation=translation,
            context=context,
            pos=pos,
        )

    def set_mastered(self, vocab_id: int, mastered: bool) -> bool:
        return self.vocabulary_repository.set_mastered(vocab_id, mastered)

    def set_mastered_by_word(self, word: str, mastered: bool, *, language_id: str = "en") -> bool:
        return self.vocabulary_repository.set_mastered_by_word(
            word,
            mastered,
            language_id=language_id,
        )

    def delete_vocabulary(self, vocab_id: int) -> bool:
        return self.vocabulary_repository.delete_vocabulary(vocab_id)

    def list_mastered_words(self, language_id: str = "en") -> list[str]:
        return self.vocabulary_repository.list_mastered_words(language_id)

    def find_mastered_words(
        self,
        language_id: str,
        candidates: set[str],
    ) -> list[str]:
        return self.vocabulary_repository.find_mastered_words(language_id, candidates)

    def count_vocabulary_for_unit(self, unit_id: str) -> int:
        return self.vocabulary_repository.count_vocabulary_for_unit(unit_id)

    def record_lookup(
        self,
        unit: ReadingUnit,
        *,
        word: str,
        was_annotated: bool = False,
    ) -> int:
        return self.reading_lookup_repository.record_lookup(
            unit,
            word=word,
            was_annotated=was_annotated,
        )

    def summarize_lookups(self, *, unit_ids):
        return self.reading_lookup_repository.summarize_lookups(unit_ids=unit_ids)

    def get_annotation_target(self, book_id: str) -> int:
        return self.reading_support_repository.get_annotation_target(book_id)

    def set_annotation_target(
        self,
        book_id: str,
        annotation_target: int,
    ) -> None:
        self.reading_support_repository.set_annotation_target(
            book_id,
            annotation_target,
        )

    def get_state(self, book_id: str) -> ReadingSupportState:
        return self.reading_support_repository.get_state(book_id)

    def save_evaluation_state(
        self,
        book_id: str,
        state: ReadingSupportState,
    ) -> None:
        self.reading_support_repository.save_evaluation_state(book_id, state)

    def list_vocabulary(
        self,
        *,
        unit_id: str | None = None,
        chapter_id: str | None = None,
        profile_id: str | None = None,
        book_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return self.vocabulary_repository.list_vocabulary(
            unit_id=unit_id,
            chapter_id=chapter_id,
            profile_id=profile_id,
            book_id=book_id,
        )

    def add_bookmark(
        self,
        unit: ReadingUnit,
        *,
        body_kind: str,
        page_index: int,
        progress_ratio: float = 0,
        total_pages: int = 0,
        label: str = "",
        excerpt: str = "",
        paragraph_index: int = -1,
    ) -> int:
        return self.bookmark_repository.add_bookmark(
            unit,
            body_kind=body_kind,
            page_index=page_index,
            progress_ratio=progress_ratio,
            total_pages=total_pages,
            label=label,
            excerpt=excerpt,
            paragraph_index=paragraph_index,
        )

    def list_bookmarks(self, *, unit_id: str | None = None) -> list[dict[str, Any]]:
        return self.bookmark_repository.list_bookmarks(unit_id=unit_id)

    def delete_bookmark(self, bookmark_id: int) -> bool:
        return self.bookmark_repository.delete_bookmark(bookmark_id)
