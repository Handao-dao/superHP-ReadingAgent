"""Transitional all-in-one SQLite storage implementation.

AppDB composes the shared connection, migration, unit, vocabulary, and bookmark
repository implementations. It contains no repository SQL and remains only as
the historical ``superhp_agent.storage.AppDB`` lifecycle and compatibility
facade.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from superhp_agent.corpus import ReadingUnit
from superhp_agent.domain.vocabulary import normalize_pos as normalize_pos
from superhp_agent.storage.database import SQLiteDatabase
from superhp_agent.storage.migrations import initialize_schema
from superhp_agent.storage.sqlite.bookmarks import (
    VALID_BODY_KINDS as VALID_BODY_KINDS,
)
from superhp_agent.storage.sqlite.bookmarks import (
    SQLiteBookmarkRepository,
)
from superhp_agent.storage.sqlite.units import SQLiteUnitRepository
from superhp_agent.storage.sqlite.vocabulary import (
    ANNOTATION_MARKER_RE as ANNOTATION_MARKER_RE,
)
from superhp_agent.storage.sqlite.vocabulary import (
    SQLiteVocabularyRepository,
)
from superhp_agent.storage.sqlite.vocabulary import (
    strip_annotation_markers as strip_annotation_markers,
)


class AppDB:
    """Compatibility facade that composes SQLite repository implementations."""

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
        self.bookmark_repository = SQLiteBookmarkRepository(
            self.database,
            sync_unit=self.unit_repository.sync,
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

    def set_mastered_by_word(self, word: str, mastered: bool, *, profile_id: str | None = None) -> bool:
        return self.vocabulary_repository.set_mastered_by_word(
            word,
            mastered,
            profile_id=profile_id,
        )

    def delete_vocabulary(self, vocab_id: int) -> bool:
        return self.vocabulary_repository.delete_vocabulary(vocab_id)

    def list_mastered_words(self) -> list[str]:
        return self.vocabulary_repository.list_mastered_words()

    def count_vocabulary_for_unit(self, unit_id: str) -> int:
        return self.vocabulary_repository.count_vocabulary_for_unit(unit_id)

    def list_vocabulary(
        self,
        *,
        unit_id: str | None = None,
        chapter_id: str | None = None,
        profile_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return self.vocabulary_repository.list_vocabulary(
            unit_id=unit_id,
            chapter_id=chapter_id,
            profile_id=profile_id,
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
    ) -> int:
        return self.bookmark_repository.add_bookmark(
            unit,
            body_kind=body_kind,
            page_index=page_index,
            progress_ratio=progress_ratio,
            total_pages=total_pages,
            label=label,
            excerpt=excerpt,
        )

    def list_bookmarks(self, *, unit_id: str | None = None) -> list[dict[str, Any]]:
        return self.bookmark_repository.list_bookmarks(unit_id=unit_id)

    def delete_bookmark(self, bookmark_id: int) -> bool:
        return self.bookmark_repository.delete_bookmark(bookmark_id)
