"""Focused tests for SQLite ownership and the reset-first current schema."""

from superhp_agent.storage import AppDB
from superhp_agent.storage.database import SQLiteDatabase
from superhp_agent.storage.migrations import initialize_schema
from superhp_agent.storage.sqlite import (
    SQLiteBookDifficultyCatalog,
    SQLiteChapterReadingCheckpointRepository,
    SQLiteReadingSupportRepository,
    SQLiteRecommendationSessionRepository,
    SQLiteUnitRepository,
)


def test_sqlite_database_configures_connection(tmp_path):
    database = SQLiteDatabase(tmp_path / "nested" / "app.db")
    try:
        assert database.path.exists()
        assert database.connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert database.connection.execute("SELECT 1").fetchone()[0] == 1
    finally:
        database.close()


def test_app_db_composes_unit_repository(tmp_path):
    db = AppDB(tmp_path / "app.db")
    try:
        assert isinstance(db.unit_repository, SQLiteUnitRepository)
        assert isinstance(db.book_difficulty_catalog, SQLiteBookDifficultyCatalog)
        assert isinstance(
            db.reading_support_repository,
            SQLiteReadingSupportRepository,
        )
        assert isinstance(
            db.chapter_checkpoint_repository,
            SQLiteChapterReadingCheckpointRepository,
        )
        assert isinstance(
            db.recommendation_session_repository,
            SQLiteRecommendationSessionRepository,
        )
    finally:
        db.close()


def test_initialize_schema_creates_current_repository_tables(tmp_path):
    database = SQLiteDatabase(tmp_path / "app.db")
    try:
        initialize_schema(database.connection)
        initialize_schema(database.connection)
        tables = {
            row["name"]
            for row in database.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert {
            "units",
            "lexemes",
            "lexeme_mastery",
            "book_vocabulary",
            "unit_vocabulary",
            "bookmarks",
            "reading_progress",
            "unit_progress",
            "recommendation_catalog",
            "recommendation_sessions",
            "reading_lookup_events",
            "book_reading_support",
            "chapter_reading_checkpoints",
        } <= tables
        assert "vocabulary" not in tables

        unit_columns = {
            row["name"]
            for row in database.connection.execute("PRAGMA table_info(units)").fetchall()
        }
        assert {"profile_id", "language_id"} <= unit_columns
        assert not {"status", "annotated_path", "annotated_at", "read_at"} & unit_columns
        support_columns = {
            row["name"]
            for row in database.connection.execute(
                "PRAGMA table_info(book_reading_support)"
            ).fetchall()
        }
        assert {
            "low_density_streak",
            "max_target_high_density_streak",
            "last_evaluated_chapter_id",
            "cooldown_chapters_remaining",
            "last_decision",
            "last_uncovered_lookup_density",
        } <= support_columns
        assert database.connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        database.close()


def test_initialize_schema_adds_adaptation_columns_to_existing_support_table(
    tmp_path,
):
    database = SQLiteDatabase(tmp_path / "app.db")
    try:
        database.connection.execute(
            """
            CREATE TABLE book_reading_support (
                book_id TEXT PRIMARY KEY,
                annotation_target INTEGER NOT NULL DEFAULT 8,
                updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            )
            """
        )
        database.connection.commit()

        initialize_schema(database.connection)

        columns = {
            row["name"]
            for row in database.connection.execute(
                "PRAGMA table_info(book_reading_support)"
            ).fetchall()
        }
        assert {
            "low_density_streak",
            "max_target_high_density_streak",
            "last_evaluated_chapter_id",
            "cooldown_chapters_remaining",
            "last_decision",
            "last_uncovered_lookup_density",
        } <= columns
    finally:
        database.close()
