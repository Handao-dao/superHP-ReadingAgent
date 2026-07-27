"""SQLite implementation of per-book annotation support persistence."""

from superhp_agent.domain.reading_support import (
    DEFAULT_ANNOTATION_TARGET,
    validate_annotation_target,
)
from superhp_agent.storage.database import SQLiteDatabase


class SQLiteReadingSupportRepository:
    """Persist one current English annotation target per corpus book."""

    def __init__(self, database: SQLiteDatabase):
        self.database = database

    def get_annotation_target(self, book_id: str) -> int:
        book_id = self._require_book_id(book_id)
        with self.database.lock:
            row = self.database.connection.execute(
                """
                SELECT annotation_target
                FROM book_reading_support
                WHERE book_id = ?
                """,
                (book_id,),
            ).fetchone()
        if row is None:
            return DEFAULT_ANNOTATION_TARGET
        return validate_annotation_target(int(row["annotation_target"]))

    def set_annotation_target(
        self,
        book_id: str,
        annotation_target: int,
    ) -> None:
        book_id = self._require_book_id(book_id)
        annotation_target = validate_annotation_target(annotation_target)
        with self.database.lock:
            self.database.connection.execute(
                """
                INSERT INTO book_reading_support (
                    book_id,
                    annotation_target,
                    updated_at
                ) VALUES (?, ?, datetime('now','localtime'))
                ON CONFLICT(book_id) DO UPDATE SET
                    annotation_target=excluded.annotation_target,
                    updated_at=excluded.updated_at
                """,
                (book_id, annotation_target),
            )
            self.database.connection.commit()

    @staticmethod
    def _require_book_id(book_id: str) -> str:
        value = str(book_id or "").strip()
        if not value:
            raise ValueError("book_id is required")
        return value
