"""SQLite implementation of bookmark persistence.

This repository owns bookmark validation and SQL. It shares a configured
SQLiteDatabase and delegates unit metadata synchronization to the composition
facade; it does not open connections, run migrations, or manage vocabulary.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from superhp_agent.corpus import ReadingUnit
from superhp_agent.storage.database import SQLiteDatabase

VALID_BODY_KINDS = {"source", "annotated"}


class SQLiteBookmarkRepository:
    """Persist and query explicit reader bookmarks in SQLite."""

    def __init__(
        self,
        database: SQLiteDatabase,
        *,
        sync_unit: Callable[[ReadingUnit], None],
    ):
        self.database = database
        self.sync_unit = sync_unit

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
        annotation_level: str = "",
        paragraph_index: int = -1,
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
        annotation_level = (
            str(annotation_level or "").strip() if body_kind == "annotated" else ""
        )
        paragraph_index = max(-1, int(paragraph_index))
        with self.database.lock:
            self.sync_unit(unit)
            cursor = self.database.connection.execute(
                """
                INSERT INTO bookmarks (
                    unit_id, chapter_id, body_kind, page_index, progress_ratio,
                    total_pages, label, excerpt, annotation_level, paragraph_index
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    annotation_level,
                    paragraph_index,
                ),
            )
            self.database.connection.commit()
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
                annotation_level,
                paragraph_index,
                created_at
            FROM bookmarks
            {where}
            ORDER BY datetime(created_at) DESC, id DESC
        """
        with self.database.lock:
            return [
                dict(row)
                for row in self.database.connection.execute(query, params).fetchall()
            ]

    def delete_bookmark(self, bookmark_id: int) -> bool:
        """Remove one explicit bookmark."""
        with self.database.lock:
            cursor = self.database.connection.execute(
                "DELETE FROM bookmarks WHERE id = ?",
                (bookmark_id,),
            )
            self.database.connection.commit()
            return cursor.rowcount > 0
