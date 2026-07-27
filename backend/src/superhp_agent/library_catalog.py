"""Validated library collection metadata stored alongside the corpus."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from superhp_agent.profiles import ProfileRegistry


class LibraryCatalogError(ValueError):
    """Raised when the library catalog cannot be parsed safely."""


@dataclass(frozen=True)
class CatalogBook:
    id: str
    order: int


@dataclass(frozen=True)
class CatalogCollection:
    id: str
    profile_id: str
    title: str
    author: str
    order: int
    books: tuple[CatalogBook, ...]
    selection_policy_id: str | None = None


class LibraryCatalogStore:
    """Load stable collection and book ordering from ``corpus/catalog.yaml``."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()

    def list_collections(self) -> list[CatalogCollection]:
        if not self.path.exists():
            return []
        raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise LibraryCatalogError("Library catalog must be a mapping")
        collections = raw.get("collections") or []
        if not isinstance(collections, list):
            raise LibraryCatalogError("Library catalog collections must be a list")

        parsed: list[CatalogCollection] = []
        collection_ids: set[str] = set()
        assigned_books: set[tuple[str, str]] = set()
        for collection_index, item in enumerate(collections, start=1):
            if not isinstance(item, dict):
                raise LibraryCatalogError("Each library collection must be a mapping")
            collection_id = _required_text(item, "id")
            profile_id = _required_text(item, "profile_id")
            title = _required_text(item, "title")
            if collection_id in collection_ids:
                raise LibraryCatalogError(f"Duplicate library collection id: {collection_id}")
            collection_ids.add(collection_id)

            book_items = item.get("books") or []
            if not isinstance(book_items, list):
                raise LibraryCatalogError(f"Collection books must be a list: {collection_id}")
            books: list[CatalogBook] = []
            local_book_ids: set[str] = set()
            for book_index, book_item in enumerate(book_items, start=1):
                if not isinstance(book_item, dict):
                    raise LibraryCatalogError(f"Collection book must be a mapping: {collection_id}")
                book_id = _required_text(book_item, "id")
                if book_id in local_book_ids:
                    raise LibraryCatalogError(f"Duplicate book id in {collection_id}: {book_id}")
                assignment = (profile_id, book_id)
                if assignment in assigned_books:
                    raise LibraryCatalogError(
                        f"Book is assigned to multiple {profile_id} collections: {book_id}"
                    )
                local_book_ids.add(book_id)
                assigned_books.add(assignment)
                books.append(
                    CatalogBook(
                        id=book_id,
                        order=_order(book_item.get("order"), book_index),
                    )
                )
            books.sort(key=lambda book: (book.order, book.id))
            parsed.append(
                CatalogCollection(
                    id=collection_id,
                    profile_id=profile_id,
                    title=title,
                    author=str(item.get("author") or "").strip(),
                    order=_order(item.get("order"), collection_index),
                    books=tuple(books),
                    selection_policy_id=_optional_text(item, "selection_policy_id"),
                )
            )
        return sorted(parsed, key=lambda collection: (collection.order, collection.id))

    def validate(self, profile_registry: ProfileRegistry) -> None:
        """Fail fast when catalog Profile or optional policy ids are invalid."""
        for collection in self.list_collections():
            try:
                profile = profile_registry.get(collection.profile_id)
            except ValueError as exc:
                raise LibraryCatalogError(
                    f"Unknown profile in library collection {collection.id}: {collection.profile_id}"
                ) from exc
            if collection.selection_policy_id is None:
                continue
            try:
                profile.build_annotator_base_context(
                    selection_policy_id=collection.selection_policy_id,
                )
            except ValueError as exc:
                raise LibraryCatalogError(
                    "Invalid selection policy in library collection "
                    f"{collection.id}: {collection.selection_policy_id}"
                ) from exc

    def selection_policy_id_for_book(
        self,
        book_id: str,
        *,
        profile_id: str | None = None,
    ) -> str | None:
        """Return the optional series prompt addition assigned to a book."""
        for collection in self.list_collections():
            if profile_id is not None and collection.profile_id != profile_id:
                continue
            if any(book.id == book_id for book in collection.books):
                return collection.selection_policy_id
        return None

    def collection_for_book(
        self,
        book_id: str,
        *,
        profile_id: str | None = None,
    ) -> CatalogCollection | None:
        """Return the local collection that owns a Corpus book."""
        for collection in self.list_collections():
            if profile_id is not None and collection.profile_id != profile_id:
                continue
            if any(book.id == book_id for book in collection.books):
                return collection
        return None


def _required_text(item: dict, key: str) -> str:
    value = str(item.get(key) or "").strip()
    if not value:
        raise LibraryCatalogError(f"Missing library catalog field: {key}")
    return value


def _optional_text(item: dict, key: str) -> str | None:
    value = str(item.get(key) or "").strip()
    return value or None


def _order(value: object, fallback: int) -> int:
    if value in (None, ""):
        return fallback
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise LibraryCatalogError(f"Invalid library catalog order: {value}") from exc
