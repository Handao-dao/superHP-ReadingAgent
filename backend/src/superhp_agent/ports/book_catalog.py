"""Book-catalog capability required by recommendation application logic.

The Port hides whether difficulty data comes from a small local catalog,
user-confirmed metadata, or a future licensed provider. Implementations must
return normalized recommendation contracts and must not expose vendor DTOs.
"""

from typing import Protocol, runtime_checkable

from superhp_agent.contracts.recommendation import (
    BookCandidate,
    BookDifficulty,
    BookSearchQuery,
)


@runtime_checkable
class BookDifficultyCatalog(Protocol):
    """Find edition difficulty and search candidate books."""

    async def find_by_isbn(self, isbn: str) -> BookDifficulty | None: ...

    async def search_books(self, query: BookSearchQuery) -> list[BookCandidate]: ...
