"""Minimal bookmark persistence capability required by HTTP application flows.

The port describes bookmark operations without prescribing SQLite tables,
transactions, migrations, transport DTOs, or vocabulary persistence.
"""

from typing import Any, Protocol, runtime_checkable

from superhp_agent.corpus import ReadingUnit


@runtime_checkable
class BookmarkRepository(Protocol):
    """Create, query, and remove explicit reader bookmarks."""

    def add_bookmark(
        self,
        unit: ReadingUnit,
        *,
        body_kind: str,
        page_index: int,
        progress_ratio: float = 0,
        total_pages: int = 0,
        label: str = "",
        excerpt: str = "",
        paragraph_index: int = -1,
    ) -> int: ...

    def list_bookmarks(self, *, unit_id: str | None = None) -> list[dict[str, Any]]: ...

    def delete_bookmark(self, bookmark_id: int) -> bool: ...
