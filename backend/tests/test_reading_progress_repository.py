from superhp_agent.contracts.reading import ReadingProgressSnapshot
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


def test_repository_imports_legacy_snapshot_only_when_empty(tmp_path):
    database, repository = make_repository(tmp_path)
    try:
        imported = repository.import_legacy(
            ReadingProgressSnapshot(
                current_unit_id="hp01-ch02",
                opened_unit_ids=["hp01-ch01", "hp01-ch02"],
                read_unit_ids=["hp01-ch01"],
            )
        )
        imported_again = repository.import_legacy(
            ReadingProgressSnapshot(current_unit_id="ignored")
        )

        snapshot = repository.load()
        assert imported is True
        assert imported_again is False
        assert snapshot.current_unit_id == "hp01-ch02"
        assert set(snapshot.opened_unit_ids) == {"hp01-ch01", "hp01-ch02"}
        assert snapshot.read_unit_ids == ["hp01-ch01"]
    finally:
        database.close()
