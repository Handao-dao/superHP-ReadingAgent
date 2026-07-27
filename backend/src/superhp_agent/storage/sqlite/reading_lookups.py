"""SQLite storage for successful reader-initiated contextual lookups.

Rows are append-only reading facts. The repository deliberately does not infer
whether a book is too difficult; that deterministic policy belongs to the
application layer and can aggregate only the reading units in its chosen
observation window.
"""

from __future__ import annotations

from collections.abc import Callable, Collection

from superhp_agent.contracts import ReadingLookupSummary
from superhp_agent.corpus import ReadingUnit
from superhp_agent.domain.vocabulary import normalize_word
from superhp_agent.storage.database import SQLiteDatabase


class SQLiteReadingLookupRepository:
    """Persist lookup clicks and return simple counts for explicit unit ids."""

    def __init__(
        self,
        database: SQLiteDatabase,
        *,
        sync_unit: Callable[[ReadingUnit], None],
    ):
        self.database = database
        self.sync_unit = sync_unit

    def record_lookup(
        self,
        unit: ReadingUnit,
        *,
        word: str,
        was_annotated: bool = False,
    ) -> int:
        normalized_word = normalize_word(word)
        if not normalized_word:
            raise ValueError("word is required")

        with self.database.lock:
            self.sync_unit(unit)
            cursor = self.database.connection.execute(
                """
                INSERT INTO reading_lookup_events (
                    unit_id,
                    chapter_id,
                    book_id,
                    normalized_word,
                    was_annotated
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    unit.id,
                    unit.chapter_id,
                    unit.book_id,
                    normalized_word,
                    int(bool(was_annotated)),
                ),
            )
            self.database.connection.commit()
            return int(cursor.lastrowid)

    def summarize_lookups(
        self,
        *,
        unit_ids: Collection[str],
    ) -> ReadingLookupSummary:
        normalized_ids = tuple(
            dict.fromkeys(
                value
                for unit_id in unit_ids
                if (value := str(unit_id or "").strip())
            )
        )
        if not normalized_ids:
            return ReadingLookupSummary()

        placeholders = ", ".join("?" for _ in normalized_ids)
        with self.database.lock:
            row = self.database.connection.execute(
                f"""
                SELECT
                    COUNT(*) AS lookup_count,
                    COUNT(DISTINCT normalized_word) AS unique_lookup_count,
                    COALESCE(SUM(was_annotated), 0) AS annotated_lookup_count
                FROM reading_lookup_events
                WHERE unit_id IN ({placeholders})
                """,
                normalized_ids,
            ).fetchone()
        return ReadingLookupSummary(
            lookup_count=int(row["lookup_count"] or 0),
            unique_lookup_count=int(row["unique_lookup_count"] or 0),
            annotated_lookup_count=int(row["annotated_lookup_count"] or 0),
        )
