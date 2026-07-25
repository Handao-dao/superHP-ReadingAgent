"""Read a small, manually maintained book-difficulty catalog from YAML.

This is the first concrete ``BookDifficultyCatalog`` adapter. It is intended
for local development and user-confirmed metadata; it does not scrape Lexile
web pages, infer a certified reader measure, modify the corpus, or rank final
recommendations on behalf of an agent.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import yaml

from superhp_agent.contracts.recommendation import (
    BookCandidate,
    BookDifficulty,
    BookSearchQuery,
)


class LocalBookCatalogError(ValueError):
    """Raised when local recommendation metadata is malformed or ambiguous."""


class LocalBookDifficultyCatalog:
    """Load and query ``corpus/book_difficulty_catalog.yaml``."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()

    def list_candidates(self) -> list[BookCandidate]:
        """Return validated candidates in deterministic difficulty order."""
        if not self.path.exists():
            return []
        raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise LocalBookCatalogError("Book difficulty catalog must be a mapping")
        if raw.get("version") != 1:
            raise LocalBookCatalogError("Unsupported book difficulty catalog version")
        items = raw.get("books") or []
        if not isinstance(items, list):
            raise LocalBookCatalogError("Book difficulty catalog books must be a list")

        candidates: list[BookCandidate] = []
        catalog_ids: set[str] = set()
        isbns: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                raise LocalBookCatalogError("Each catalog book must be a mapping")
            candidate = _parse_candidate(item)
            if candidate.catalog_id in catalog_ids:
                raise LocalBookCatalogError(
                    f"Duplicate book catalog id: {candidate.catalog_id}"
                )
            catalog_ids.add(candidate.catalog_id)
            if candidate.isbn:
                if candidate.isbn in isbns:
                    raise LocalBookCatalogError(
                        f"Duplicate book catalog ISBN: {candidate.isbn}"
                    )
                isbns.add(candidate.isbn)
            candidates.append(candidate)

        return sorted(
            candidates,
            key=lambda candidate: (
                _candidate_measure(candidate),
                candidate.title.casefold(),
                candidate.catalog_id,
            ),
        )

    async def find_by_isbn(self, isbn: str) -> BookDifficulty | None:
        """Return edition-specific difficulty after lenient query normalization."""
        normalized = _normalize_isbn(isbn, strict=False)
        if normalized is None:
            return None
        for candidate in self.list_candidates():
            if candidate.isbn == normalized:
                return candidate.difficulty
        return None

    async def search_books(self, query: BookSearchQuery) -> list[BookCandidate]:
        """Apply catalog-neutral filters without performing recommendation ranking."""
        requested_categories = {item.casefold() for item in query.categories}
        excluded_isbns = {
            normalized
            for item in query.excluded_isbns
            if (normalized := _normalize_isbn(item, strict=False)) is not None
        }
        results: list[BookCandidate] = []
        for candidate in self.list_candidates():
            measure = _candidate_measure(candidate)
            if query.lexile_min is not None and measure < query.lexile_min:
                continue
            if query.lexile_max is not None and measure > query.lexile_max:
                continue
            if requested_categories and not requested_categories.intersection(
                genre.casefold() for genre in candidate.genres
            ):
                continue
            if query.fiction is not None and candidate.fiction is not query.fiction:
                continue
            has_series = candidate.series_title is not None
            if query.series_only is not None and has_series is not query.series_only:
                continue
            if candidate.isbn is not None and candidate.isbn in excluded_isbns:
                continue
            results.append(candidate)
            if len(results) >= query.limit:
                break
        return results


def _parse_candidate(item: dict) -> BookCandidate:
    catalog_id = _required_text(item, "id")
    title = _required_text(item, "title")
    isbn = _normalize_isbn(_optional_text(item, "isbn"), strict=True)
    lexile = item.get("lexile")
    if not isinstance(lexile, dict):
        raise LocalBookCatalogError(f"Missing Lexile metadata for book: {catalog_id}")
    source = _required_text(lexile, "source")
    is_certified = _optional_bool(lexile, "certified", False)
    if is_certified and isbn is None:
        raise LocalBookCatalogError(
            f"Certified Lexile metadata requires an ISBN: {catalog_id}"
        )
    difficulty = BookDifficulty(
        isbn=isbn,
        lexile_measure=_required_int(lexile, "measure"),
        source=source,
        lexile_code=_optional_text(lexile, "code"),
        is_certified=is_certified,
        verified_at=_optional_datetime(lexile, "verified_at"),
    )
    series = item.get("series")
    if series is not None and not isinstance(series, dict):
        raise LocalBookCatalogError(f"Book series must be a mapping: {catalog_id}")
    series = series or {}
    local_book_id = _optional_text(item, "local_book_id")
    return BookCandidate(
        catalog_id=catalog_id,
        title=title,
        author=str(item.get("author") or "").strip(),
        isbn=isbn,
        difficulty=difficulty,
        genres=_text_tuple(item, "genres"),
        series_title=_optional_text(series, "title"),
        series_index=_optional_positive_int(series, "index"),
        page_count=_optional_positive_int(item, "page_count"),
        summary=str(item.get("summary") or "").strip(),
        source_url=_optional_text(item, "source_url"),
        fiction=_optional_bool(item, "fiction", True),
        local_book_id=local_book_id,
        available_locally=local_book_id is not None,
    )


def _candidate_measure(candidate: BookCandidate) -> int:
    difficulty = candidate.difficulty
    if difficulty is None:
        raise LocalBookCatalogError(
            f"Candidate has no difficulty measure: {candidate.catalog_id}"
        )
    return difficulty.lexile_measure


def _required_text(item: dict, key: str) -> str:
    value = str(item.get(key) or "").strip()
    if not value:
        raise LocalBookCatalogError(f"Missing book catalog field: {key}")
    return value


def _optional_text(item: dict, key: str) -> str | None:
    value = str(item.get(key) or "").strip()
    return value or None


def _required_int(item: dict, key: str) -> int:
    value = item.get(key)
    if isinstance(value, bool):
        raise LocalBookCatalogError(f"Invalid integer book catalog field: {key}")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise LocalBookCatalogError(
            f"Invalid integer book catalog field: {key}"
        ) from exc


def _optional_positive_int(item: dict, key: str) -> int | None:
    if item.get(key) in (None, ""):
        return None
    value = _required_int(item, key)
    if value <= 0:
        raise LocalBookCatalogError(
            f"Book catalog field must be positive: {key}"
        )
    return value


def _optional_bool(item: dict, key: str, default: bool) -> bool:
    value = item.get(key, default)
    if not isinstance(value, bool):
        raise LocalBookCatalogError(f"Invalid boolean book catalog field: {key}")
    return value


def _optional_datetime(item: dict, key: str) -> datetime | None:
    value = _optional_text(item, key)
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LocalBookCatalogError(
            f"Invalid ISO datetime book catalog field: {key}"
        ) from exc


def _text_tuple(item: dict, key: str) -> tuple[str, ...]:
    values = item.get(key) or []
    if not isinstance(values, list):
        raise LocalBookCatalogError(f"Book catalog field must be a list: {key}")
    normalized: list[str] = []
    for value in values:
        text = str(value or "").strip().casefold()
        if not text:
            raise LocalBookCatalogError(f"Book catalog {key} contains an empty value")
        if text not in normalized:
            normalized.append(text)
    return tuple(normalized)


def _normalize_isbn(value: object, *, strict: bool) -> str | None:
    text = str(value or "").strip().upper()
    if not text:
        return None
    normalized = text.replace("-", "").replace(" ", "")
    valid = (
        len(normalized) == 13
        and normalized.isdigit()
        or len(normalized) == 10
        and normalized[:-1].isdigit()
        and (normalized[-1].isdigit() or normalized[-1] == "X")
    )
    if valid:
        return normalized
    if strict:
        raise LocalBookCatalogError(f"Invalid ISBN: {text}")
    return None
