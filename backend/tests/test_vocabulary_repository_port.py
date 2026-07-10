"""Boundary tests for the minimal vocabulary repository capability."""

from superhp_agent.ports import VocabularyRepository
from superhp_agent.storage import AppDB


def test_app_db_satisfies_vocabulary_repository_port(tmp_path):
    db = AppDB(tmp_path / "app.db")

    try:
        assert isinstance(db, VocabularyRepository)
        assert db.list_mastered_words() == []
        assert db.count_vocabulary_for_unit("missing-unit") == 0
    finally:
        db.close()
