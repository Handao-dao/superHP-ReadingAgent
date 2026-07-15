"""SQLite implementation of single-user reading progress persistence.

The singleton table owns the current pointer; ``unit_progress`` owns opened and
read timestamps.
"""

from superhp_agent.contracts.reading import ReadingProgressSnapshot
from superhp_agent.storage.database import SQLiteDatabase


class SQLiteReadingProgressRepository:
    """Persist current, opened, and read state on the shared SQLite connection."""

    def __init__(self, database: SQLiteDatabase):
        self.database = database

    def load(self) -> ReadingProgressSnapshot:
        with self.database.lock:
            current = self.database.connection.execute(
                "SELECT current_unit_id FROM reading_progress WHERE id = 1"
            ).fetchone()
            rows = self.database.connection.execute(
                "SELECT unit_id, opened_at, read_at FROM unit_progress"
            ).fetchall()
        return ReadingProgressSnapshot(
            current_unit_id=str(current["current_unit_id"] or "") if current else "",
            opened_unit_ids=[str(row["unit_id"]) for row in rows if row["opened_at"]],
            read_unit_ids=[str(row["unit_id"]) for row in rows if row["read_at"]],
        )

    def mark_opened(self, unit_id: str) -> ReadingProgressSnapshot:
        unit_id = self._require_unit_id(unit_id)
        with self.database.lock:
            self._mark_opened(unit_id)
            self.database.connection.commit()
        return self.load()

    def mark_read(self, unit_id: str) -> ReadingProgressSnapshot:
        unit_id = self._require_unit_id(unit_id)
        with self.database.lock:
            self._mark_opened(unit_id)
            self.database.connection.execute(
                "UPDATE unit_progress SET read_at = COALESCE(read_at, datetime('now')) WHERE unit_id = ?",
                (unit_id,),
            )
            self.database.connection.commit()
        return self.load()

    def _mark_opened(self, unit_id: str) -> None:
        self.database.connection.execute(
            """
            INSERT INTO unit_progress (unit_id, opened_at)
            VALUES (?, datetime('now'))
            ON CONFLICT(unit_id) DO UPDATE SET
                opened_at=COALESCE(unit_progress.opened_at, excluded.opened_at)
            """,
            (unit_id,),
        )
        self.database.connection.execute(
            """
            INSERT INTO reading_progress (id, current_unit_id, last_opened_at)
            VALUES (1, ?, datetime('now'))
            ON CONFLICT(id) DO UPDATE SET
                current_unit_id=excluded.current_unit_id,
                last_opened_at=excluded.last_opened_at
            """,
            (unit_id,),
        )

    @staticmethod
    def _require_unit_id(unit_id: str) -> str:
        value = str(unit_id or "").strip()
        if not value:
            raise ValueError("unit_id is required")
        return value
