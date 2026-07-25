"""Tests for the manually maintained YAML book-difficulty adapter."""

from pathlib import Path

import pytest

from superhp_agent.contracts import BookSearchQuery
from superhp_agent.local_book_catalog import (
    LocalBookCatalogError,
    LocalBookDifficultyCatalog,
)
from superhp_agent.ports import BookDifficultyCatalog

CATALOG_YAML = """
version: 1
books:
  - id: easy-mystery
    local_book_id: local-easy
    title: Easy Mystery
    author: A. Writer
    isbn: "978-0-00-000000-1"
    fiction: true
    genres: [mystery, detective]
    series:
      title: Easy Cases
      index: 1
    page_count: 180
    lexile:
      measure: 700
      certified: true
      source: user_supplied
      verified_at: 2026-07-25
  - id: middle-mystery
    title: Middle Mystery
    author: B. Writer
    isbn: "9780000000002"
    fiction: true
    genres: [mystery]
    lexile:
      measure: 800
      certified: false
      source: user_supplied
  - id: fantasy-challenge
    title: Fantasy Challenge
    author: C. Writer
    isbn: "9780000000003"
    fiction: true
    genres: [fantasy]
    series:
      title: Fantasy Series
      index: 2
    lexile:
      measure: 900
      certified: true
      source: user_supplied
""".strip()


def write_catalog(tmp_path: Path, content: str = CATALOG_YAML) -> Path:
    path = tmp_path / "book_difficulty_catalog.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def test_local_catalog_is_a_book_difficulty_catalog_port(tmp_path: Path):
    catalog = LocalBookDifficultyCatalog(write_catalog(tmp_path))

    assert isinstance(catalog, BookDifficultyCatalog)


@pytest.mark.asyncio
async def test_local_catalog_normalizes_isbn_and_returns_difficulty(tmp_path: Path):
    catalog = LocalBookDifficultyCatalog(write_catalog(tmp_path))

    difficulty = await catalog.find_by_isbn("978 0 00 000000 1")

    assert difficulty is not None
    assert difficulty.isbn == "9780000000001"
    assert difficulty.lexile_measure == 700
    assert difficulty.is_certified is True
    assert difficulty.verified_at is not None


@pytest.mark.asyncio
async def test_local_catalog_filters_range_genre_series_and_exclusions(tmp_path: Path):
    catalog = LocalBookDifficultyCatalog(write_catalog(tmp_path))

    results = await catalog.search_books(
        BookSearchQuery(
            lexile_min=650,
            lexile_max=850,
            categories=("MYSTERY",),
            fiction=True,
            series_only=True,
            excluded_isbns=("9780000000002",),
        )
    )

    assert [candidate.catalog_id for candidate in results] == ["easy-mystery"]
    assert results[0].local_book_id == "local-easy"
    assert results[0].available_locally is True


@pytest.mark.asyncio
async def test_local_catalog_returns_stable_difficulty_order_and_limit(tmp_path: Path):
    catalog = LocalBookDifficultyCatalog(write_catalog(tmp_path))

    results = await catalog.search_books(BookSearchQuery(limit=2))

    assert [candidate.catalog_id for candidate in results] == [
        "easy-mystery",
        "middle-mystery",
    ]


@pytest.mark.asyncio
async def test_missing_local_catalog_behaves_as_empty_catalog(tmp_path: Path):
    catalog = LocalBookDifficultyCatalog(tmp_path / "missing.yaml")

    assert catalog.list_candidates() == []
    assert await catalog.find_by_isbn("9780000000001") is None
    assert await catalog.search_books(BookSearchQuery()) == []


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("version: 2\nbooks: []", "version"),
        (
            """
version: 1
books:
  - id: duplicate
    title: First
    lexile: {measure: 700, source: test}
  - id: duplicate
    title: Second
    lexile: {measure: 800, source: test}
""",
            "Duplicate book catalog id",
        ),
        (
            """
version: 1
books:
  - id: first
    title: First
    isbn: "9780000000001"
    lexile: {measure: 700, source: test}
  - id: second
    title: Second
    isbn: "978-0-00-000000-1"
    lexile: {measure: 800, source: test}
""",
            "Duplicate book catalog ISBN",
        ),
        (
            """
version: 1
books:
  - id: missing-edition
    title: Missing Edition
    lexile:
      measure: 700
      source: test
      certified: true
""",
            "requires an ISBN",
        ),
        (
            """
version: 1
books:
  - id: invalid-isbn
    title: Invalid ISBN
    isbn: "123"
    lexile: {measure: 700, source: test}
""",
            "Invalid ISBN",
        ),
    ],
)
def test_local_catalog_rejects_ambiguous_or_invalid_metadata(
    tmp_path: Path,
    content: str,
    message: str,
):
    catalog = LocalBookDifficultyCatalog(write_catalog(tmp_path, content.strip()))

    with pytest.raises(LocalBookCatalogError, match=message):
        catalog.list_candidates()
