"""SQLite storage for immutable completed-chapter checkpoints."""

from __future__ import annotations

import json
from typing import Any

from superhp_agent.contracts import ChapterReadingCheckpoint
from superhp_agent.storage.database import SQLiteDatabase


class SQLiteChapterReadingCheckpointRepository:
    """Insert one snapshot per chapter and preserve the first completion facts."""

    def __init__(self, database: SQLiteDatabase):
        self.database = database

    def record(
        self,
        checkpoint: ChapterReadingCheckpoint,
    ) -> ChapterReadingCheckpoint | None:
        with self.database.lock:
            cursor = self.database.connection.execute(
                """
                INSERT OR IGNORE INTO chapter_reading_checkpoints (
                    book_id,
                    chapter_id,
                    chapter_no,
                    unit_ids_json,
                    word_count,
                    lookup_count,
                    annotated_lookup_count,
                    annotation_target
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    checkpoint.book_id,
                    checkpoint.chapter_id,
                    checkpoint.chapter_no,
                    json.dumps(checkpoint.unit_ids, ensure_ascii=False),
                    checkpoint.word_count,
                    checkpoint.lookup_count,
                    checkpoint.annotated_lookup_count,
                    checkpoint.annotation_target,
                ),
            )
            if cursor.rowcount != 1:
                self.database.connection.commit()
                return None
            row = self.database.connection.execute(
                """
                SELECT *
                FROM chapter_reading_checkpoints
                WHERE book_id = ? AND chapter_id = ?
                """,
                (checkpoint.book_id, checkpoint.chapter_id),
            ).fetchone()
            self.database.connection.commit()
        return _checkpoint_from_row(row)

    def list_for_book(
        self,
        book_id: str,
    ) -> tuple[ChapterReadingCheckpoint, ...]:
        book_id = self._require_book_id(book_id)
        with self.database.lock:
            rows = self.database.connection.execute(
                """
                SELECT *
                FROM chapter_reading_checkpoints
                WHERE book_id = ?
                ORDER BY chapter_no, completed_at, chapter_id
                """,
                (book_id,),
            ).fetchall()
        return tuple(_checkpoint_from_row(row) for row in rows)

    def latest_for_book(
        self,
        book_id: str,
        *,
        limit: int = 3,
    ) -> tuple[ChapterReadingCheckpoint, ...]:
        """Return the latest completed chapters in chronological order."""
        book_id = self._require_book_id(book_id)
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        with self.database.lock:
            rows = self.database.connection.execute(
                """
                SELECT *
                FROM chapter_reading_checkpoints
                WHERE book_id = ?
                ORDER BY completed_at DESC, chapter_no DESC, chapter_id DESC
                LIMIT ?
                """,
                (book_id, limit),
            ).fetchall()
        return tuple(_checkpoint_from_row(row) for row in reversed(rows))

    @staticmethod
    def _require_book_id(book_id: str) -> str:
        value = str(book_id or "").strip()
        if not value:
            raise ValueError("book_id is required")
        return value


def _checkpoint_from_row(row: Any) -> ChapterReadingCheckpoint:
    unit_ids = json.loads(str(row["unit_ids_json"]))
    return ChapterReadingCheckpoint(
        book_id=str(row["book_id"]),
        chapter_id=str(row["chapter_id"]),
        chapter_no=int(row["chapter_no"]),
        unit_ids=tuple(str(unit_id) for unit_id in unit_ids),
        word_count=int(row["word_count"]),
        lookup_count=int(row["lookup_count"]),
        annotated_lookup_count=int(row["annotated_lookup_count"]),
        annotation_target=(
            int(row["annotation_target"])
            if row["annotation_target"] is not None
            else None
        ),
        completed_at=str(row["completed_at"]),
    )
