"""Transitional all-in-one SQLite storage implementation.

AppDB now composes the shared connection, migration, and vocabulary repository
boundaries, but still contains unit metadata and bookmark SQL. Repository Ports
already hide it from upper layers; upcoming steps will extract those remaining
queries without changing the historical ``superhp_agent.storage.AppDB`` import.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from superhp_agent.corpus import ReadingUnit
from superhp_agent.domain.vocabulary import normalize_pos as normalize_pos
from superhp_agent.storage.database import SQLiteDatabase
from superhp_agent.storage.migrations import initialize_schema
from superhp_agent.storage.sqlite.vocabulary import (
    ANNOTATION_MARKER_RE as ANNOTATION_MARKER_RE,
)
from superhp_agent.storage.sqlite.vocabulary import (
    SQLiteVocabularyRepository,
)
from superhp_agent.storage.sqlite.vocabulary import (
    strip_annotation_markers as strip_annotation_markers,
)

VALID_BODY_KINDS = {"source", "annotated"}


class AppDB:
    """Thin SQLite gateway used by services and API endpoints."""
    def __init__(self, db_path: str | Path):
        self.database = SQLiteDatabase(db_path)
        self.path = self.database.path
        # Compatibility references while repository SQL remains in AppDB.
        self._conn = self.database.connection
        self._lock = self.database.lock
        initialize_schema(self._conn)
        self.vocabulary_repository = SQLiteVocabularyRepository(
            self.database,
            sync_unit=self.sync_unit,
        )

    def close(self) -> None:
        self.database.close()

    def sync_unit(self, unit: ReadingUnit) -> None:
        """Upsert corpus metadata so vocabulary rows can reference a unit."""
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO units (
                    id, chapter_id, book_id, book_title, chapter_no, chapter_title,
                    section_no, section_count, summary, source_path, profile_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    chapter_id=excluded.chapter_id,
                    book_id=excluded.book_id,
                    book_title=excluded.book_title,
                    chapter_no=excluded.chapter_no,
                    chapter_title=excluded.chapter_title,
                    section_no=excluded.section_no,
                    section_count=excluded.section_count,
                    summary=excluded.summary,
                    source_path=excluded.source_path,
                    profile_id=excluded.profile_id
                """,
                (
                    unit.id,
                    unit.chapter_id,
                    unit.book_id,
                    unit.book_title,
                    unit.chapter_no,
                    unit.chapter_title,
                    unit.section_no,
                    unit.section_count,
                    unit.summary,
                    str(unit.path),
                    unit.profile_id,
                ),
            )
            self._conn.commit()

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
        """Store one explicit reading bookmark and return its id."""
        body_kind = str(body_kind or "").strip()
        if body_kind not in VALID_BODY_KINDS:
            raise ValueError("body_kind must be source or annotated")
        page_index = max(0, int(page_index))
        total_pages = max(0, int(total_pages))
        progress_ratio = min(1, max(0, float(progress_ratio)))
        label = str(label or "").strip()
        excerpt = str(excerpt or "").strip()
        with self._lock:
            self.sync_unit(unit)
            cursor = self._conn.execute(
                """
                INSERT INTO bookmarks (
                    unit_id, chapter_id, body_kind, page_index, progress_ratio,
                    total_pages, label, excerpt
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    unit.id,
                    unit.chapter_id,
                    body_kind,
                    page_index,
                    progress_ratio,
                    total_pages,
                    label,
                    excerpt,
                ),
            )
            self._conn.commit()
            return int(cursor.lastrowid)

    def list_bookmarks(self, *, unit_id: str | None = None) -> list[dict[str, Any]]:
        """Return explicit reading bookmarks, newest first."""
        params: list[str] = []
        where = ""
        if unit_id:
            where = "WHERE unit_id = ?"
            params.append(unit_id)
        query = f"""
            SELECT
                id,
                unit_id,
                chapter_id,
                body_kind,
                page_index,
                progress_ratio,
                total_pages,
                label,
                excerpt,
                created_at
            FROM bookmarks
            {where}
            ORDER BY datetime(created_at) DESC, id DESC
        """
        with self._lock:
            return [dict(row) for row in self._conn.execute(query, params).fetchall()]

    def delete_bookmark(self, bookmark_id: int) -> bool:
        """Remove one explicit bookmark."""
        with self._lock:
            cursor = self._conn.execute("DELETE FROM bookmarks WHERE id = ?", (bookmark_id,))
            self._conn.commit()
            return cursor.rowcount > 0
