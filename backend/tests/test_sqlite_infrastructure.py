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
        initialize_schema(database.connection)
        tables = {
            row["name"]
            for row in database.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert {"units", "vocabulary", "unit_vocabulary", "bookmarks"} <= tables
        unit_columns = {
            row["name"]
            for row in database.connection.execute("PRAGMA table_info(units)").fetchall()
        }
        assert not {"status", "annotated_path", "annotated_at", "read_at"} & unit_columns
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
            CREATE TABLE bookmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unit_id TEXT NOT NULL,
                chapter_id TEXT NOT NULL,
                body_kind TEXT NOT NULL,
                page_index INTEGER NOT NULL DEFAULT 0,
                progress_ratio REAL NOT NULL DEFAULT 0,
                total_pages INTEGER NOT NULL DEFAULT 0,
                label TEXT DEFAULT '',
                excerpt TEXT DEFAULT '',
                created_at TEXT
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
        bookmark_columns = {
            row["name"]
            for row in database.connection.execute("PRAGMA table_info(bookmarks)").fetchall()
        }
        assert "pos" in vocabulary_columns
        assert {"profile_id", "normalized_word"} <= vocabulary_columns
        assert "profile_id" in unit_columns
        assert {"annotation_level", "paragraph_index"} <= bookmark_columns
    finally:
        database.close()


def test_initialize_schema_preserves_legacy_unit_runtime_columns(tmp_path):
    database = SQLiteDatabase(tmp_path / "legacy-units.db")

    try:
        initialize_schema(database.connection)
        database.connection.execute("ALTER TABLE units ADD COLUMN status TEXT DEFAULT 'unread'")
        database.connection.execute("ALTER TABLE units ADD COLUMN annotated_path TEXT DEFAULT ''")
        database.connection.execute("ALTER TABLE units ADD COLUMN annotated_at TEXT DEFAULT NULL")
        database.connection.execute("ALTER TABLE units ADD COLUMN read_at TEXT DEFAULT NULL")

        initialize_schema(database.connection)

        unit_columns = {
            row["name"]
            for row in database.connection.execute("PRAGMA table_info(units)").fetchall()
        }
        assert {"status", "annotated_path", "annotated_at", "read_at"} <= unit_columns
    finally:
        database.close()


def test_legacy_global_vocabulary_is_split_by_unit_profile(tmp_path):
    database = SQLiteDatabase(tmp_path / "legacy-profile.db")

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
                profile_id TEXT NOT NULL,
                source_path TEXT NOT NULL
            );
            CREATE TABLE vocabulary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT NOT NULL UNIQUE,
                translation TEXT NOT NULL,
                pos TEXT NOT NULL DEFAULT 'other',
                mastered INTEGER DEFAULT 0,
                mastered_at TEXT DEFAULT NULL,
                first_seen_at TEXT,
                last_seen_at TEXT
            );
            CREATE TABLE unit_vocabulary (
                unit_id TEXT NOT NULL,
                chapter_id TEXT NOT NULL,
                vocab_id INTEGER NOT NULL,
                translation TEXT NOT NULL,
                context TEXT DEFAULT '',
                encounter_count INTEGER DEFAULT 1,
                first_seen_at TEXT,
                last_seen_at TEXT,
                PRIMARY KEY (unit_id, vocab_id)
            );
            INSERT INTO units (
                id, chapter_id, book_id, book_title, chapter_no, chapter_title,
                profile_id, source_path
            ) VALUES
                ('en-01', 'en-01', 'en', 'English', 1, 'One', 'english_novel', 'en.md'),
                ('cc-01', 'cc-01', 'cc', '古文', 1, '一', 'classical_chinese', 'cc.md');
            INSERT INTO vocabulary (id, word, translation, mastered)
            VALUES (1, 'Master', '旧翻译', 1);
            INSERT INTO unit_vocabulary (unit_id, chapter_id, vocab_id, translation)
            VALUES
                ('en-01', 'en-01', 1, '主人'),
                ('cc-01', 'cc-01', 1, '掌握');
            """
        )

        initialize_schema(database.connection)
        initialize_schema(database.connection)

        rows = database.connection.execute(
            """
            SELECT profile_id, normalized_word, mastered
            FROM vocabulary ORDER BY profile_id
            """
        ).fetchall()
        assert [tuple(row) for row in rows] == [
            ("classical_chinese", "master", 1),
            ("english_novel", "master", 1),
        ]
        linked_profiles = database.connection.execute(
            """
            SELECT u.profile_id
            FROM unit_vocabulary uv
            JOIN units u ON u.id = uv.unit_id
            JOIN vocabulary v ON v.id = uv.vocab_id
            WHERE u.profile_id = v.profile_id
            ORDER BY u.profile_id
            """
        ).fetchall()
        assert [row["profile_id"] for row in linked_profiles] == [
            "classical_chinese",
            "english_novel",
        ]
        assert database.connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        database.close()
