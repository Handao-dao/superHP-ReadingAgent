"""Boundary tests for the book-difficulty catalog Port."""

from superhp_agent.contracts import BookCandidate, BookDifficulty, BookSearchQuery
from superhp_agent.ports import BookDifficultyCatalog


class MinimalBookCatalog:
    async def find_by_id(self, catalog_id: str):
        return BookCandidate(
            catalog_id=catalog_id,
            title_en="Book",
            difficulty=BookDifficulty(760, 760),
        )

    async def search_books(self, query: BookSearchQuery):
        return [
            BookCandidate(
                catalog_id="book-1",
                title_en="Book",
                difficulty=BookDifficulty(760, 760),
                genres=query.categories,
            )
        ]


def test_minimal_book_catalog_satisfies_application_port():
    assert isinstance(MinimalBookCatalog(), BookDifficultyCatalog)
