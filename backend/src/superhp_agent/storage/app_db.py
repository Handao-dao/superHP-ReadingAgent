"""Transitional all-in-one SQLite storage implementation.

AppDB now composes the shared connection and migration boundaries, but still
contains unit metadata, vocabulary, and bookmark SQL. Repository Ports already
hide it from upper layers; upcoming steps will extract those query
implementations without changing the historical ``superhp_agent.storage.AppDB``
import.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from superhp_agent.corpus import ReadingUnit
from superhp_agent.domain.vocabulary import normalize_pos as normalize_pos
from superhp_agent.storage.database import SQLiteDatabase
from superhp_agent.storage.migrations import initialize_schema

ANNOTATION_MARKER_RE = re.compile(r"\[\[([^|\]]+)\|[^|\]]+(?:\|[^|\]]+)?\]\]")
VALID_BODY_KINDS = {"source", "annotated"}


def strip_annotation_markers(text: str) -> str:
    """Return source text with inline annotation markers removed."""
    return ANNOTATION_MARKER_RE.sub(r"\1", text)


class AppDB:
    """Thin SQLite gateway used by services and API endpoints."""
    def __init__(self, db_path: str | Path):
        self.database = SQLiteDatabase(db_path)
        self.path = self.database.path
        # Compatibility references while repository SQL remains in AppDB.
        self._conn = self.database.connection
        self._lock = self.database.lock
        initialize_schema(self._conn)

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
        """Store extracted vocabulary and its unit-specific encounter context."""
        inserted = 0
        with self._lock:
            self.sync_unit(unit)
            for item in items:
                word = str(getattr(item, "word", "") or "").strip()
                translation = str(getattr(item, "translation", "") or "").strip()
                context = strip_annotation_markers(str(getattr(item, "context", "") or "")).strip()
                pos = normalize_pos(getattr(item, "pos", "other"))
                if not word or not translation:
                    continue
                self._conn.execute(
                    """
                    INSERT INTO vocabulary (word, translation, pos)
                    VALUES (?, ?, ?)
                    ON CONFLICT(word) DO UPDATE SET
                        translation=excluded.translation,
                        pos=CASE
                            WHEN vocabulary.pos IN ('other', '其他') THEN excluded.pos
                            ELSE vocabulary.pos
                        END,
                        last_seen_at=datetime('now','localtime')
                    """,
                    (word, translation, pos),
                )
                vocab_id = self._conn.execute(
                    "SELECT id FROM vocabulary WHERE word = ?",
                    (word,),
                ).fetchone()["id"]
                self._conn.execute(
                    """
                    INSERT INTO unit_vocabulary (unit_id, chapter_id, vocab_id, translation, context)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(unit_id, vocab_id) DO UPDATE SET
                        translation=excluded.translation,
                        context=excluded.context,
                        encounter_count=unit_vocabulary.encounter_count + 1,
                        last_seen_at=datetime('now','localtime')
                    """,
                    (unit.id, unit.chapter_id, vocab_id, translation, context),
                )
                inserted += 1
            self._conn.commit()
        return inserted

    def add_manual_vocabulary(
        self,
        unit: ReadingUnit,
        *,
        word: str,
        translation: str,
        context: str = "",
        pos: str = "other",
    ) -> int:
        """Store one user-selected lookup result and return its vocabulary id."""
        word = word.strip()
        translation = translation.strip()
        context = strip_annotation_markers(context).strip()
        pos = normalize_pos(pos)
        if not word or not translation:
            raise ValueError("word and translation are required")

        with self._lock:
            self.sync_unit(unit)
            self._conn.execute(
                """
                INSERT INTO vocabulary (word, translation, pos, mastered, mastered_at)
                VALUES (?, ?, ?, 0, NULL)
                ON CONFLICT(word) DO UPDATE SET
                    translation=excluded.translation,
                    pos=excluded.pos,
                    mastered=0,
                    mastered_at=NULL,
                    last_seen_at=datetime('now','localtime')
                """,
                (word, translation, pos),
            )
            vocab_id = int(
                self._conn.execute(
                    "SELECT id FROM vocabulary WHERE word = ?",
                    (word,),
                ).fetchone()["id"]
            )
            self._conn.execute(
                """
                INSERT INTO unit_vocabulary (unit_id, chapter_id, vocab_id, translation, context)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(unit_id, vocab_id) DO UPDATE SET
                    translation=excluded.translation,
                    context=excluded.context,
                    last_seen_at=datetime('now','localtime')
                """,
                (unit.id, unit.chapter_id, vocab_id, translation, context),
            )
            self._conn.commit()
            return vocab_id

    def set_mastered(self, vocab_id: int, mastered: bool) -> bool:
        """Mark one vocabulary item mastered or active."""
        with self._lock:
            cursor = self._conn.execute(
                """
                UPDATE vocabulary
                SET mastered = ?,
                    mastered_at = CASE WHEN ? THEN datetime('now','localtime') ELSE NULL END,
                    last_seen_at = datetime('now','localtime')
                WHERE id = ?
                """,
                (1 if mastered else 0, 1 if mastered else 0, vocab_id),
            )
            self._conn.commit()
            return cursor.rowcount > 0

    def set_mastered_by_word(self, word: str, mastered: bool, *, profile_id: str | None = None) -> bool:
        """Mark vocabulary by word, used by inline reading actions."""
        normalized = word.strip().lower()
        if not normalized:
            return False
        with self._lock:
            profile_clause = ""
            params: list[Any] = [1 if mastered else 0, 1 if mastered else 0, normalized]
            if profile_id:
                profile_clause = """
                    AND EXISTS (
                        SELECT 1
                        FROM unit_vocabulary uv
                        JOIN units u ON u.id = uv.unit_id
                        WHERE uv.vocab_id = vocabulary.id AND u.profile_id = ?
                    )
                """
                params.append(profile_id)
            cursor = self._conn.execute(
                f"""
                UPDATE vocabulary
                SET mastered = ?,
                    mastered_at = CASE WHEN ? THEN datetime('now','localtime') ELSE NULL END,
                    last_seen_at = datetime('now','localtime')
                WHERE lower(word) = ?
                {profile_clause}
                """,
                params,
            )
            self._conn.commit()
            return cursor.rowcount > 0

    def delete_vocabulary(self, vocab_id: int) -> bool:
        """Remove a vocabulary item and its unit links."""
        with self._lock:
            cursor = self._conn.execute("DELETE FROM vocabulary WHERE id = ?", (vocab_id,))
            self._conn.commit()
            return cursor.rowcount > 0

    def list_mastered_words(self) -> list[str]:
        """Return globally mastered words for prompt context."""
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT word
                FROM vocabulary
                WHERE mastered = 1
                ORDER BY lower(word)
                """
            ).fetchall()
            return [str(row["word"]) for row in rows]

    def count_vocabulary_for_unit(self, unit_id: str) -> int:
        """Return the number shown on guided cards for one reading unit."""
        with self._lock:
            row = self._conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM unit_vocabulary uv
                JOIN vocabulary v ON v.id = uv.vocab_id
                WHERE uv.unit_id = ? AND v.mastered = 0
                """,
                (unit_id,),
            ).fetchone()
            return int(row["count"] if row else 0)

    def list_vocabulary(
        self,
        *,
        unit_id: str | None = None,
        chapter_id: str | None = None,
        profile_id: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[str] = []
        if unit_id:
            clauses.append("uv.unit_id = ?")
            params.append(unit_id)
        if chapter_id:
            clauses.append("uv.chapter_id = ?")
            params.append(chapter_id)
        if profile_id:
            clauses.append("u.profile_id = ?")
            params.append(profile_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT
                v.id,
                v.word,
                v.translation AS global_translation,
                v.pos,
                v.mastered,
                uv.translation,
                uv.context,
                uv.encounter_count,
                uv.unit_id,
                uv.chapter_id,
                uv.first_seen_at,
                uv.last_seen_at
            FROM unit_vocabulary uv
            JOIN vocabulary v ON v.id = uv.vocab_id
            JOIN units u ON u.id = uv.unit_id
            {where}
            ORDER BY uv.last_seen_at DESC, lower(v.word)
        """
        with self._lock:
            return [dict(row) for row in self._conn.execute(query, params).fetchall()]

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
