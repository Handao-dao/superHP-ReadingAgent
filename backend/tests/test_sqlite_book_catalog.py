"""Tests for the SQLite book-recommendation catalog adapter."""

import pytest

from superhp_agent.contracts import (
    BookCandidate,
    BookDifficulty,
    BookEntryKind,
    BookSearchQuery,
)
from superhp_agent.ports import BookDifficultyCatalog
from superhp_agent.storage.database import SQLiteDatabase
from superhp_agent.storage.migrations import initialize_schema
from superhp_agent.storage.sqlite import SQLiteBookDifficultyCatalog


def make_catalog(tmp_path):
    database = SQLiteDatabase(tmp_path / "catalog.sqlite3")
    initialize_schema(database.connection)
    catalog = SQLiteBookDifficultyCatalog(database)
    catalog.upsert_many(
        [
            BookCandidate(
                catalog_id="easy-mystery",
                title_en="Easy Mystery",
                title_zh="简单谜案",
                author="A. Writer",
                difficulty=BookDifficulty(500, 500),
                entry_kind=BookEntryKind.BOOK,
                genres=("mystery", "detective"),
                raw_text="500L Easy Mystery 简单谜案",
            ),
            BookCandidate(
                catalog_id="mystery-series",
                title_en="Mystery Series",
                title_zh="谜案系列",
                difficulty=BookDifficulty(600, 800),
                entry_kind=BookEntryKind.SERIES,
                genres=("mystery",),
            ),
            BookCandidate(
                catalog_id="fantasy-book",
                title_en="Fantasy Book",
                difficulty=BookDifficulty(900, 900),
                entry_kind=BookEntryKind.BOOK,
                genres=("fantasy",),
            ),
        ]
    )
    return database, catalog


def test_sqlite_catalog_satisfies_book_catalog_port(tmp_path):
    database, catalog = make_catalog(tmp_path)
    try:
        assert isinstance(catalog, BookDifficultyCatalog)
        assert catalog.count() == 3
    finally:
        database.close()


@pytest.mark.asyncio
async def test_sqlite_catalog_finds_normalized_entry_by_id(tmp_path):
    database, catalog = make_catalog(tmp_path)
    try:
        candidate = await catalog.find_by_id("easy-mystery")

        assert candidate is not None
        assert candidate.title_zh == "简单谜案"
        assert candidate.difficulty.exact_measure == 500
        assert candidate.raw_text == "500L Easy Mystery 简单谜案"
    finally:
        database.close()


@pytest.mark.asyncio
async def test_sqlite_catalog_searches_overlapping_ranges_and_genres(tmp_path):
    database, catalog = make_catalog(tmp_path)
    try:
        results = await catalog.search_books(
            BookSearchQuery(
                lexile_min=700,
                lexile_max=850,
                categories=("MYSTERY",),
                entry_kinds=(BookEntryKind.SERIES,),
            )
        )

        assert [candidate.catalog_id for candidate in results] == ["mystery-series"]
    finally:
        database.close()


@pytest.mark.asyncio
async def test_sqlite_catalog_applies_exclusions_and_limit_after_genre_filter(
    tmp_path,
):
    database, catalog = make_catalog(tmp_path)
    try:
        results = await catalog.search_books(
            BookSearchQuery(
                categories=("mystery",),
                excluded_ids=("easy-mystery",),
                limit=1,
            )
        )

        assert [candidate.catalog_id for candidate in results] == ["mystery-series"]
    finally:
        database.close()


def test_sqlite_catalog_upserts_and_replaces_prototype_data(tmp_path):
    database, catalog = make_catalog(tmp_path)
    try:
        updated = BookCandidate(
            catalog_id="easy-mystery",
            title_en="Updated Mystery",
            difficulty=BookDifficulty(520, 520),
            entry_kind=BookEntryKind.BOOK,
        )
        assert catalog.upsert_many([updated]) == 1
        assert catalog.count() == 3

        assert catalog.replace_all([updated]) == 1
        assert catalog.count() == 1
        row = database.connection.execute(
            "SELECT title_en, lexile_min FROM recommendation_catalog"
        ).fetchone()
        assert dict(row) == {"title_en": "Updated Mystery", "lexile_min": 520}
    finally:
        database.close()
