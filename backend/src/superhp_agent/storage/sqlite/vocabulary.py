"""SQLite vocabulary storage with book isolation and language-wide mastery."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from superhp_agent.corpus import ReadingUnit
from superhp_agent.domain.vocabulary import normalize_pos, normalize_word
from superhp_agent.storage.database import SQLiteDatabase

ANNOTATION_MARKER_RE = re.compile(r"\[\[([^|\]]+)\|[^|\]]+(?:\|[^|\]]+)?\]\]")


def strip_annotation_markers(text: str) -> str:
    return ANNOTATION_MARKER_RE.sub(r"\1", text)


class SQLiteVocabularyRepository:
    """Persist book-local vocabulary and language-wide mastery state."""

    def __init__(self, database: SQLiteDatabase, *, sync_unit: Callable[[ReadingUnit], None]):
        self.database = database
        self.sync_unit = sync_unit

    def _ensure_lexeme(self, unit: ReadingUnit, word: str) -> int:
        normalized = normalize_word(word)
        self.database.connection.execute(
            """
            INSERT INTO lexemes (language_id, normalized_word, display_word)
            VALUES (?, ?, ?)
            ON CONFLICT(language_id, normalized_word) DO UPDATE SET
                display_word=excluded.display_word,
                updated_at=datetime('now','localtime')
            """,
            (unit.language_id, normalized, word),
        )
        return int(
            self.database.connection.execute(
                "SELECT id FROM lexemes WHERE language_id = ? AND normalized_word = ?",
                (unit.language_id, normalized),
            ).fetchone()["id"]
        )

    def _ensure_book_vocabulary(
        self,
        unit: ReadingUnit,
        *,
        lexeme_id: int,
        translation: str,
        pos: str,
    ) -> int:
        self.database.connection.execute(
            """
            INSERT INTO book_vocabulary (book_id, profile_id, lexeme_id, translation, pos)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(book_id, lexeme_id) DO UPDATE SET
                profile_id=excluded.profile_id,
                translation=excluded.translation,
                pos=CASE
                    WHEN book_vocabulary.pos IN ('other', '其他') THEN excluded.pos
                    ELSE book_vocabulary.pos
                END,
                last_seen_at=datetime('now','localtime')
            """,
            (unit.book_id, unit.profile_id, lexeme_id, translation, pos),
        )
        return int(
            self.database.connection.execute(
                "SELECT id FROM book_vocabulary WHERE book_id = ? AND lexeme_id = ?",
                (unit.book_id, lexeme_id),
            ).fetchone()["id"]
        )

    def add_vocabulary_items(self, unit: ReadingUnit, items: list[Any]) -> int:
        inserted = 0
        with self.database.lock:
            self.sync_unit(unit)
            for item in items:
                word = str(getattr(item, "word", "") or "").strip()
                translation = str(getattr(item, "translation", "") or "").strip()
                context = strip_annotation_markers(str(getattr(item, "context", "") or "")).strip()
                pos = normalize_pos(getattr(item, "pos", "other"))
                if not normalize_word(word) or not translation:
                    continue
                lexeme_id = self._ensure_lexeme(unit, word)
                book_vocab_id = self._ensure_book_vocabulary(
                    unit,
                    lexeme_id=lexeme_id,
                    translation=translation,
                    pos=pos,
                )
                self.database.connection.execute(
                    """
                    INSERT INTO unit_vocabulary (
                        unit_id, chapter_id, book_vocab_id, translation, context
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(unit_id, book_vocab_id) DO UPDATE SET
                        translation=excluded.translation,
                        context=excluded.context,
                        encounter_count=unit_vocabulary.encounter_count + 1,
                        last_seen_at=datetime('now','localtime')
                    """,
                    (unit.id, unit.chapter_id, book_vocab_id, translation, context),
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
        word = word.strip()
        translation = translation.strip()
        if not normalize_word(word) or not translation:
            raise ValueError("word and translation are required")
        with self.database.lock:
            self.sync_unit(unit)
            lexeme_id = self._ensure_lexeme(unit, word)
            book_vocab_id = self._ensure_book_vocabulary(
                unit,
                lexeme_id=lexeme_id,
                translation=translation,
                pos=normalize_pos(pos),
            )
            self.database.connection.execute(
                """
                INSERT INTO unit_vocabulary (
                    unit_id, chapter_id, book_vocab_id, translation, context
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(unit_id, book_vocab_id) DO UPDATE SET
                    translation=excluded.translation,
                    context=excluded.context,
                    last_seen_at=datetime('now','localtime')
                """,
                (unit.id, unit.chapter_id, book_vocab_id, translation, strip_annotation_markers(context).strip()),
            )
            self.database.connection.commit()
            return book_vocab_id

    def set_mastered(self, book_vocab_id: int, mastered: bool) -> bool:
        with self.database.lock:
            row = self.database.connection.execute(
                "SELECT lexeme_id FROM book_vocabulary WHERE id = ?",
                (book_vocab_id,),
            ).fetchone()
            if row is None:
                return False
            self.database.connection.execute(
                """
                INSERT INTO lexeme_mastery (lexeme_id, mastered, mastered_at, updated_at)
                VALUES (?, ?, CASE WHEN ? THEN datetime('now','localtime') ELSE NULL END, datetime('now','localtime'))
                ON CONFLICT(lexeme_id) DO UPDATE SET
                    mastered=excluded.mastered,
                    mastered_at=excluded.mastered_at,
                    updated_at=excluded.updated_at
                """,
                (row["lexeme_id"], int(mastered), int(mastered)),
            )
            self.database.connection.commit()
            return True

    def set_mastered_by_word(self, word: str, mastered: bool, *, language_id: str) -> bool:
        normalized = normalize_word(word)
        if not normalized:
            return False
        with self.database.lock:
            row = self.database.connection.execute(
                "SELECT id FROM lexemes WHERE language_id = ? AND normalized_word = ?",
                (language_id, normalized),
            ).fetchone()
            if row is None:
                return False
            self.database.connection.execute(
                """
                INSERT INTO lexeme_mastery (lexeme_id, mastered, mastered_at, updated_at)
                VALUES (?, ?, CASE WHEN ? THEN datetime('now','localtime') ELSE NULL END, datetime('now','localtime'))
                ON CONFLICT(lexeme_id) DO UPDATE SET
                    mastered=excluded.mastered,
                    mastered_at=excluded.mastered_at,
                    updated_at=excluded.updated_at
                """,
                (row["id"], int(mastered), int(mastered)),
            )
            self.database.connection.commit()
            return True

    def delete_vocabulary(self, book_vocab_id: int) -> bool:
        with self.database.lock:
            cursor = self.database.connection.execute(
                "DELETE FROM book_vocabulary WHERE id = ?",
                (book_vocab_id,),
            )
            self.database.connection.commit()
            return cursor.rowcount > 0

    def list_mastered_words(self, language_id: str = "en") -> list[str]:
        with self.database.lock:
            rows = self.database.connection.execute(
                """
                SELECT l.display_word
                FROM lexemes l
                JOIN lexeme_mastery m ON m.lexeme_id = l.id
                WHERE l.language_id = ? AND m.mastered = 1
                ORDER BY l.normalized_word
                """,
                (language_id,),
            ).fetchall()
            return [str(row["display_word"]) for row in rows]

    def find_mastered_words(self, language_id: str, candidates: set[str]) -> list[str]:
        normalized = sorted({value for word in candidates if (value := normalize_word(word))})
        if not normalized:
            return []
        found: dict[str, str] = {}
        with self.database.lock:
            for start in range(0, len(normalized), 400):
                batch = normalized[start : start + 400]
                placeholders = ", ".join("?" for _ in batch)
                rows = self.database.connection.execute(
                    f"""
                    SELECT l.normalized_word, l.display_word
                    FROM lexemes l
                    JOIN lexeme_mastery m ON m.lexeme_id = l.id
                    WHERE l.language_id = ? AND m.mastered = 1
                      AND l.normalized_word IN ({placeholders})
                    """,
                    [language_id, *batch],
                ).fetchall()
                found.update((str(row["normalized_word"]), str(row["display_word"])) for row in rows)
        return [found[key] for key in sorted(found)]

    def count_vocabulary_for_unit(self, unit_id: str) -> int:
        with self.database.lock:
            row = self.database.connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM unit_vocabulary uv
                JOIN book_vocabulary bv ON bv.id = uv.book_vocab_id
                LEFT JOIN lexeme_mastery m ON m.lexeme_id = bv.lexeme_id
                WHERE uv.unit_id = ? AND COALESCE(m.mastered, 0) = 0
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
        book_id: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[str] = []
        for column, value in (
            ("uv.unit_id", unit_id),
            ("uv.chapter_id", chapter_id),
            ("bv.profile_id", profile_id),
            ("bv.book_id", book_id),
        ):
            if value:
                clauses.append(f"{column} = ?")
                params.append(value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT bv.id, bv.book_id, bv.profile_id, l.language_id,
                l.display_word AS word, bv.translation AS global_translation,
                bv.pos, COALESCE(m.mastered, 0) AS mastered,
                uv.translation, uv.context, uv.encounter_count,
                uv.unit_id, uv.chapter_id, uv.first_seen_at, uv.last_seen_at
            FROM unit_vocabulary uv
            JOIN book_vocabulary bv ON bv.id = uv.book_vocab_id
            JOIN lexemes l ON l.id = bv.lexeme_id
            LEFT JOIN lexeme_mastery m ON m.lexeme_id = l.id
            {where}
            ORDER BY uv.last_seen_at DESC, l.normalized_word
        """
        with self.database.lock:
            return [dict(row) for row in self.database.connection.execute(query, params).fetchall()]
