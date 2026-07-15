from superhp_agent.storage.database import SQLiteDatabase
from superhp_agent.storage.migrations import initialize_schema
from superhp_agent.storage.sqlite.reading_progress import (
    SQLiteReadingProgressRepository,
)


def make_repository(tmp_path):
    database = SQLiteDatabase(tmp_path / "progress.sqlite3")
    initialize_schema(database.connection)
    return database, SQLiteReadingProgressRepository(database)


def test_repository_tracks_current_opened_and_read_units(tmp_path):
    database, repository = make_repository(tmp_path)
    try:
        repository.mark_opened("hp01-ch01")
        repository.mark_read("hp01-ch01")
        repository.mark_opened("hp01-ch02")

        snapshot = repository.load()

        assert snapshot.current_unit_id == "hp01-ch02"
        assert set(snapshot.opened_unit_ids) == {"hp01-ch01", "hp01-ch02"}
        assert snapshot.read_unit_ids == ["hp01-ch01"]
    finally:
        database.close()
