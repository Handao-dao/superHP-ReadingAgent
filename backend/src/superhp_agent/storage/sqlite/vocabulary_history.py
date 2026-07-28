"""SQLite reader for exact vocabulary contexts authorized by Agent scope.

This adapter joins existing vocabulary and unit metadata into typed encounters.
It does not normalize model input, choose accessible units, compare meanings,
or generate an Agent response.
"""

from __future__ import annotations

import sqlite3

from superhp_agent.contracts import VocabularyEncounter
from superhp_agent.ports.repositories import (
    VocabularyHistoryRepositoryError,
)
from superhp_agent.storage.database import SQLiteDatabase


class SQLiteVocabularyHistoryRepository:
    """Read recent stored contexts without exposing raw SQLite rows."""

    def __init__(self, database: SQLiteDatabase):
        self.database = database

    def find_encounters(
        self,
        *,
        language_id: str,
        normalized_word: str,
        book_id: str,
        allowed_unit_ids: tuple[str, ...],
        limit: int,
    ) -> tuple[VocabularyEncounter, ...]:
        language_id = str(language_id or "").strip()
        normalized_word = str(normalized_word or "").strip()
        book_id = str(book_id or "").strip()
        if not language_id or not normalized_word or not book_id:
            raise ValueError(
                "language_id, normalized_word, and book_id are required"
            )
        if limit < 1:
            raise ValueError("limit must be positive")

        unit_ids = tuple(
            dict.fromkeys(
                str(unit_id or "").strip()
                for unit_id in allowed_unit_ids
                if str(unit_id or "").strip()
            )
        )
        if not unit_ids:
            return ()

        placeholders = ", ".join("?" for _ in unit_ids)
        query = f"""
            SELECT
                bv.book_id,
                uv.chapter_id,
                u.chapter_no,
                uv.unit_id,
                l.display_word AS word,
                l.normalized_word,
                uv.translation,
                uv.context,
                bv.pos,
                uv.encounter_count,
                COALESCE(m.mastered, 0) AS mastered,
                uv.first_seen_at,
                uv.last_seen_at,
                u.section_no
            FROM unit_vocabulary uv
            JOIN book_vocabulary bv ON bv.id = uv.book_vocab_id
            JOIN lexemes l ON l.id = bv.lexeme_id
            JOIN units u ON u.id = uv.unit_id
            LEFT JOIN lexeme_mastery m ON m.lexeme_id = l.id
            WHERE l.language_id = ?
              AND l.normalized_word = ?
              AND bv.book_id = ?
              AND u.book_id = ?
              AND uv.chapter_id = u.chapter_id
              AND TRIM(uv.translation) <> ''
              AND TRIM(uv.context) <> ''
              AND uv.unit_id IN ({placeholders})
            ORDER BY
                u.chapter_no DESC,
                u.section_no DESC,
                uv.last_seen_at DESC,
                uv.unit_id DESC
            LIMIT ?
        """
        params = (
            language_id,
            normalized_word,
            book_id,
            book_id,
            *unit_ids,
            limit,
        )
        try:
            with self.database.lock:
                rows = self.database.connection.execute(
                    query,
                    params,
                ).fetchall()
        except sqlite3.Error as exc:
            raise VocabularyHistoryRepositoryError(
                "Unable to read vocabulary history."
            ) from exc

        encounters = tuple(
            VocabularyEncounter(
                book_id=str(row["book_id"]),
                chapter_id=str(row["chapter_id"]),
                chapter_no=int(row["chapter_no"]),
                unit_id=str(row["unit_id"]),
                word=str(row["word"]),
                normalized_word=str(row["normalized_word"]),
                translation=str(row["translation"]),
                context=str(row["context"]),
                pos=str(row["pos"]),
                encounter_count=int(row["encounter_count"]),
                mastered=bool(row["mastered"]),
                first_seen_at=str(row["first_seen_at"] or ""),
                last_seen_at=str(row["last_seen_at"] or ""),
            )
            for row in reversed(rows)
        )
        return encounters
