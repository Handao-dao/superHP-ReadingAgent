from pathlib import Path

import pytest

from superhp_agent.library_catalog import LibraryCatalogError, LibraryCatalogStore


def test_catalog_orders_collections_and_books(tmp_path: Path):
    path = tmp_path / "catalog.yaml"
    path.write_text(
        """
collections:
  - id: second
    profile_id: english_novel
    selection_policy_id: harry_potter
    title: Second
    order: 20
    books:
      - id: book-b
        order: 2
      - id: book-a
        order: 1
  - id: first
    profile_id: english_novel
    title: First
    order: 10
    books: []
""".strip(),
        encoding="utf-8",
    )

    collections = LibraryCatalogStore(path).list_collections()

    assert [item.id for item in collections] == ["first", "second"]
    assert [book.id for book in collections[1].books] == ["book-a", "book-b"]
    assert collections[0].selection_policy_id is None
    assert collections[1].selection_policy_id == "harry_potter"

    catalog = LibraryCatalogStore(path)
    assert catalog.selection_policy_id_for_book("book-a") == "harry_potter"
    assert catalog.selection_policy_id_for_book("book-a", profile_id="classical_chinese") is None
    assert catalog.selection_policy_id_for_book("missing") is None


def test_catalog_rejects_book_assigned_twice_in_one_profile(tmp_path: Path):
    path = tmp_path / "catalog.yaml"
    path.write_text(
        """
collections:
  - id: first
    profile_id: english_novel
    title: First
    books:
      - id: shared
  - id: second
    profile_id: english_novel
    title: Second
    books:
      - id: shared
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(LibraryCatalogError, match="multiple"):
        LibraryCatalogStore(path).list_collections()
