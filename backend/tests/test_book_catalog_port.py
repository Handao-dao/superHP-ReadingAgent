"""Boundary tests for the book-difficulty catalog Port."""

from superhp_agent.contracts import BookCandidate, BookDifficulty, BookSearchQuery
from superhp_agent.ports import BookDifficultyCatalog


class MinimalBookCatalog:
    async def find_by_isbn(self, isbn: str):
        return BookDifficulty(
            isbn=isbn,
            lexile_measure=760,
            source="test",
        )

    async def search_books(self, query: BookSearchQuery):
        return [
            BookCandidate(
                catalog_id="book-1",
                title="Book",
                genres=query.categories,
            )
        ]


def test_minimal_book_catalog_satisfies_application_port():
    assert isinstance(MinimalBookCatalog(), BookDifficultyCatalog)
