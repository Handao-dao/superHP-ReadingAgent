"""SQLite persistence for corpus unit metadata referenced by repositories.

This internal repository upserts the relational unit record shared by
vocabulary and bookmark rows. It does not scan corpus files, expose an
application Port, open connections, or run migrations.
"""

from superhp_agent.corpus import ReadingUnit
from superhp_agent.storage.database import SQLiteDatabase


class SQLiteUnitRepository:
    """Synchronize immutable corpus metadata into the relational database."""

    def __init__(self, database: SQLiteDatabase):
        self.database = database

    def sync(self, unit: ReadingUnit) -> None:
        """Upsert corpus metadata so relational records can reference a unit."""
        with self.database.lock:
            self.database.connection.execute(
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
            self.database.connection.commit()
