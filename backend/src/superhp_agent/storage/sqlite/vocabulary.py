"""SQLite implementation of vocabulary persistence.

This repository owns vocabulary and unit-vocabulary SQL. It shares a configured
SQLiteDatabase and delegates unit metadata synchronization to the composition
facade; it does not open connections, run migrations, or manage bookmarks.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from superhp_agent.corpus import ReadingUnit
from superhp_agent.domain.vocabulary import normalize_pos, normalize_word
from superhp_agent.storage.database import SQLiteDatabase

ANNOTATION_MARKER_RE = re.compile(r"\[\[([^|\]]+)\|[^|\]]+(?:\|[^|\]]+)?\]\]")


def strip_annotation_markers(text: str) -> str:
    """Return source text with inline annotation markers removed."""
    return ANNOTATION_MARKER_RE.sub(r"\1", text)


class SQLiteVocabularyRepository:
    """Persist and query vocabulary through one shared SQLite connection."""

    def __init__(
        self,
        database: SQLiteDatabase,
        *,
        sync_unit: Callable[[ReadingUnit], None],
    ):
        self.database = database
        self.sync_unit = sync_unit

    def add_vocabulary_items(self, unit: ReadingUnit, items: list[Any]) -> int:
        """Store extracted vocabulary and its unit-specific encounter context."""
        inserted = 0
        with self.database.lock:
            self.sync_unit(unit)
            for item in items:
                word = str(getattr(item, "word", "") or "").strip()
                translation = str(getattr(item, "translation", "") or "").strip()
                context = strip_annotation_markers(
                    str(getattr(item, "context", "") or "")
                ).strip()
                pos = normalize_pos(getattr(item, "pos", "other"))
                normalized_word = normalize_word(word)
                if not normalized_word or not translation:
                    continue
                self.database.connection.execute(
                    """
                    INSERT INTO vocabulary (
                        profile_id, normalized_word, word, translation, pos
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(profile_id, normalized_word) DO UPDATE SET
                        word=excluded.word,
                        translation=excluded.translation,
                        pos=CASE
                            WHEN vocabulary.pos IN ('other', '其他') THEN excluded.pos
                            ELSE vocabulary.pos
                        END,
                        last_seen_at=datetime('now','localtime')
                    """,
                    (unit.profile_id, normalized_word, word, translation, pos),
                )
                vocab_id = self.database.connection.execute(
                    """
                    SELECT id FROM vocabulary
                    WHERE profile_id = ? AND normalized_word = ?
                    """,
                    (unit.profile_id, normalized_word),
                ).fetchone()["id"]
                self.database.connection.execute(
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
            self.database.connection.commit()
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
        normalized_word = normalize_word(word)
        translation = translation.strip()
        context = strip_annotation_markers(context).strip()
        pos = normalize_pos(pos)
        if not normalized_word or not translation:
            raise ValueError("word and translation are required")

        with self.database.lock:
            self.sync_unit(unit)
            self.database.connection.execute(
                """
                INSERT INTO vocabulary (
                    profile_id, normalized_word, word, translation, pos,
                    mastered, mastered_at
                ) VALUES (?, ?, ?, ?, ?, 0, NULL)
                ON CONFLICT(profile_id, normalized_word) DO UPDATE SET
                    word=excluded.word,
                    translation=excluded.translation,
                    pos=excluded.pos,
                    mastered=0,
                    mastered_at=NULL,
                    last_seen_at=datetime('now','localtime')
                """,
                (unit.profile_id, normalized_word, word, translation, pos),
            )
            vocab_id = int(
                self.database.connection.execute(
                    """
                    SELECT id FROM vocabulary
                    WHERE profile_id = ? AND normalized_word = ?
                    """,
                    (unit.profile_id, normalized_word),
                ).fetchone()["id"]
            )
            self.database.connection.execute(
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
            self.database.connection.commit()
            return vocab_id

    def set_mastered(self, vocab_id: int, mastered: bool) -> bool:
        """Mark one vocabulary item mastered or active."""
        with self.database.lock:
            cursor = self.database.connection.execute(
                """
                UPDATE vocabulary
                SET mastered = ?,
                    mastered_at = CASE WHEN ? THEN datetime('now','localtime') ELSE NULL END,
                    last_seen_at = datetime('now','localtime')
                WHERE id = ?
                """,
                (1 if mastered else 0, 1 if mastered else 0, vocab_id),
            )
            self.database.connection.commit()
            return cursor.rowcount > 0

    def set_mastered_by_word(
        self,
        word: str,
        mastered: bool,
        *,
        profile_id: str | None = None,
    ) -> bool:
        """Mark vocabulary by word, used by inline reading actions."""
        normalized = normalize_word(word)
        if not normalized:
            return False
        with self.database.lock:
            resolved_profile_id = profile_id or "english_novel"
            params: list[Any] = [
                1 if mastered else 0,
                1 if mastered else 0,
                resolved_profile_id,
                normalized,
            ]
            cursor = self.database.connection.execute(
                """
                UPDATE vocabulary
                SET mastered = ?,
                    mastered_at = CASE WHEN ? THEN datetime('now','localtime') ELSE NULL END,
                    last_seen_at = datetime('now','localtime')
                WHERE profile_id = ? AND normalized_word = ?
                """,
                params,
            )
            self.database.connection.commit()
            return cursor.rowcount > 0

    def delete_vocabulary(self, vocab_id: int) -> bool:
        """Remove a vocabulary item and its unit links."""
        with self.database.lock:
            cursor = self.database.connection.execute(
                "DELETE FROM vocabulary WHERE id = ?",
                (vocab_id,),
            )
            self.database.connection.commit()
            return cursor.rowcount > 0

    def list_mastered_words(self, profile_id: str = "english_novel") -> list[str]:
        """Return mastered words for one annotation profile."""
        with self.database.lock:
            rows = self.database.connection.execute(
                """
                SELECT word
                FROM vocabulary
                WHERE profile_id = ? AND mastered = 1
                ORDER BY normalized_word
                """,
                (profile_id,),
            ).fetchall()
            return [str(row["word"]) for row in rows]

    def count_vocabulary_for_unit(self, unit_id: str) -> int:
        """Return the number shown on guided cards for one reading unit."""
        with self.database.lock:
            row = self.database.connection.execute(
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
            clauses.append("v.profile_id = ?")
            params.append(profile_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT
                v.id,
                v.profile_id,
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
            ORDER BY uv.last_seen_at DESC, v.normalized_word
        """
        with self.database.lock:
            return [
                dict(row)
                for row in self.database.connection.execute(query, params).fetchall()
            ]
