"""SQLite adapter for the local book-recommendation catalog.

The adapter owns deterministic catalog queries and bulk import writes. It does
not infer genres, parse pasted source text, run an agent, or decide which book
should be recommended.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from superhp_agent.contracts.recommendation import (
    BookCandidate,
    BookDifficulty,
    BookEntryKind,
    BookSearchQuery,
)
from superhp_agent.storage.database import SQLiteDatabase


class SQLiteBookDifficultyCatalog:
    """Store and search the small, single-user recommendation catalog."""

    def __init__(self, database: SQLiteDatabase):
        self.database = database

    async def find_by_id(self, catalog_id: str) -> BookCandidate | None:
        """Return one normalized catalog entry by stable id."""
        with self.database.lock:
            row = self.database.connection.execute(
                "SELECT * FROM recommendation_catalog WHERE id = ?",
                (catalog_id,),
            ).fetchone()
        return _row_to_candidate(row) if row is not None else None

    async def search_books(self, query: BookSearchQuery) -> list[BookCandidate]:
        """Search overlapping Lexile ranges and match any requested genre."""
        clauses: list[str] = []
        params: list[object] = []
        if query.lexile_min is not None:
            clauses.append("lexile_max >= ?")
            params.append(query.lexile_min)
        if query.lexile_max is not None:
            clauses.append("lexile_min <= ?")
            params.append(query.lexile_max)
        if query.entry_kinds:
            placeholders = ", ".join("?" for _ in query.entry_kinds)
            clauses.append(f"entry_kind IN ({placeholders})")
            params.extend(kind.value for kind in query.entry_kinds)
        if query.excluded_ids:
            placeholders = ", ".join("?" for _ in query.excluded_ids)
            clauses.append(f"id NOT IN ({placeholders})")
            params.extend(query.excluded_ids)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.database.lock:
            rows = self.database.connection.execute(
                f"""
                SELECT *
                FROM recommendation_catalog
                {where}
                ORDER BY lexile_min, lexile_max, title_en COLLATE NOCASE, id
                """,
                params,
            ).fetchall()

        requested_genres = {genre.casefold() for genre in query.categories}
        results: list[BookCandidate] = []
        for row in rows:
            candidate = _row_to_candidate(row)
            if requested_genres and not requested_genres.intersection(
                genre.casefold() for genre in candidate.genres
            ):
                continue
            results.append(candidate)
            if len(results) >= query.limit:
                break
        return results

    def upsert_many(self, candidates: Iterable[BookCandidate]) -> int:
        """Insert or update normalized candidates by stable catalog id."""
        rows = [_candidate_to_row(candidate) for candidate in candidates]
        if not rows:
            return 0
        with self.database.lock, self.database.connection:
            self.database.connection.executemany(
                """
                INSERT INTO recommendation_catalog (
                    id,
                    title_en,
                    title_zh,
                    author,
                    entry_kind,
                    lexile_min,
                    lexile_max,
                    genres_json,
                    raw_text
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title_en = excluded.title_en,
                    title_zh = excluded.title_zh,
                    author = excluded.author,
                    entry_kind = excluded.entry_kind,
                    lexile_min = excluded.lexile_min,
                    lexile_max = excluded.lexile_max,
                    genres_json = excluded.genres_json,
                    raw_text = excluded.raw_text
                """,
                rows,
            )
        return len(rows)

    def replace_all(self, candidates: Iterable[BookCandidate]) -> int:
        """Replace disposable prototype catalog data in one transaction."""
        rows = [_candidate_to_row(candidate) for candidate in candidates]
        with self.database.lock, self.database.connection:
            self.database.connection.execute("DELETE FROM recommendation_catalog")
            if rows:
                self.database.connection.executemany(
                    """
                    INSERT INTO recommendation_catalog (
                        id,
                        title_en,
                        title_zh,
                        author,
                        entry_kind,
                        lexile_min,
                        lexile_max,
                        genres_json,
                        raw_text
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
        return len(rows)

    def count(self) -> int:
        """Return the number of locally stored recommendation entries."""
        with self.database.lock:
            row = self.database.connection.execute(
                "SELECT COUNT(*) AS count FROM recommendation_catalog"
            ).fetchone()
        return int(row["count"])


def _candidate_to_row(candidate: BookCandidate) -> tuple[object, ...]:
    return (
        candidate.catalog_id,
        candidate.title_en,
        candidate.title_zh,
        candidate.author,
        candidate.entry_kind.value,
        candidate.difficulty.minimum_lexile,
        candidate.difficulty.maximum_lexile,
        json.dumps(candidate.genres, ensure_ascii=False),
        candidate.raw_text,
    )


def _row_to_candidate(row) -> BookCandidate:
    return BookCandidate(
        catalog_id=str(row["id"]),
        title_en=str(row["title_en"]),
        title_zh=str(row["title_zh"]),
        author=str(row["author"]),
        entry_kind=BookEntryKind(str(row["entry_kind"])),
        difficulty=BookDifficulty(
            minimum_lexile=int(row["lexile_min"]),
            maximum_lexile=int(row["lexile_max"]),
        ),
        genres=tuple(json.loads(str(row["genres_json"]))),
        raw_text=str(row["raw_text"]),
    )
