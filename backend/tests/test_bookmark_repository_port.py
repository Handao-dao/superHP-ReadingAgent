"""Boundary tests for the minimal bookmark repository capability."""

from superhp_agent.ports import BookmarkRepository
from superhp_agent.storage import AppDB


def test_app_db_satisfies_bookmark_repository_port(tmp_path):
    db = AppDB(tmp_path / "app.db")

    try:
        assert isinstance(db, BookmarkRepository)
        assert db.list_bookmarks() == []
        assert db.delete_bookmark(404) is False
    finally:
        db.close()
