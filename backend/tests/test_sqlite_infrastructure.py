"""Focused tests for SQLite connection ownership and schema migration."""

from superhp_agent.storage import AppDB
from superhp_agent.storage.database import SQLiteDatabase
from superhp_agent.storage.migrations import initialize_schema
from superhp_agent.storage.sqlite import SQLiteUnitRepository


def test_sqlite_database_configures_connection(tmp_path):
    database = SQLiteDatabase(tmp_path / "nested" / "app.db")

    try:
        assert database.path.exists()
        assert database.connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        row = database.connection.execute("SELECT 1 AS value").fetchone()
        assert row["value"] == 1
    finally:
        database.close()


def test_app_db_composes_unit_repository(tmp_path):
    db = AppDB(tmp_path / "app.db")

    try:
        assert isinstance(db.unit_repository, SQLiteUnitRepository)
    finally:
        db.close()


def test_initialize_schema_creates_repository_tables(tmp_path):
    database = SQLiteDatabase(tmp_path / "app.db")

    try:
        initialize_schema(database.connection)
        tables = {
            row["name"]
            for row in database.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert {"units", "vocabulary", "unit_vocabulary", "bookmarks"} <= tables
    finally:
        database.close()


def test_initialize_schema_upgrades_legacy_columns(tmp_path):
    database = SQLiteDatabase(tmp_path / "legacy.db")

    try:
        database.connection.executescript(
            """
            CREATE TABLE units (
                id TEXT PRIMARY KEY,
                chapter_id TEXT NOT NULL,
                book_id TEXT NOT NULL,
                book_title TEXT NOT NULL,
                chapter_no INTEGER NOT NULL,
                chapter_title TEXT NOT NULL,
                section_no INTEGER NOT NULL DEFAULT 1,
                section_count INTEGER NOT NULL DEFAULT 1,
                summary TEXT DEFAULT '',
                source_path TEXT NOT NULL
            );
            CREATE TABLE vocabulary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT NOT NULL UNIQUE,
                translation TEXT NOT NULL,
                mastered INTEGER DEFAULT 0
            );
            """
        )

        initialize_schema(database.connection)

        vocabulary_columns = {
            row["name"]
            for row in database.connection.execute("PRAGMA table_info(vocabulary)").fetchall()
        }
        unit_columns = {
            row["name"]
            for row in database.connection.execute("PRAGMA table_info(units)").fetchall()
        }
        assert "pos" in vocabulary_columns
        assert "profile_id" in unit_columns
    finally:
        database.close()
