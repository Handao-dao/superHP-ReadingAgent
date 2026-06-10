"""Safe reading-unit corpus loading for Markdown + YAML frontmatter."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class ReadingUnit:
    """One readable section in the local novel corpus."""

    id: str
    chapter_id: str
    book_id: str
    book_title: str
    chapter_no: int
    chapter_title: str
    section_no: int
    section_count: int
    summary: str
    path: Path

    @property
    def summary_zh(self) -> str:
        """Compatibility alias for older code paths."""
        return self.summary


@dataclass(frozen=True)
class ReadingUnitDocument:
    meta: ReadingUnit
    body: str


CorpusChapter = ReadingUnit
ChapterDocument = ReadingUnitDocument


class CorpusError(ValueError):
    pass


class CorpusStore:
    """Read markdown reading units from a single corpus root."""

    def __init__(self, corpus_dir: str | Path):
        self.corpus_dir = Path(corpus_dir).expanduser().resolve()
        self._units: dict[str, ReadingUnit] | None = None

    def list_units(self) -> list[ReadingUnit]:
        self._ensure_loaded()
        assert self._units is not None
        return sorted(
            self._units.values(),
            key=lambda item: (item.book_id, item.chapter_no, item.section_no, item.id),
        )

    def get_unit(self, unit_id: str) -> ReadingUnitDocument:
        self._ensure_loaded()
        assert self._units is not None
        unit = self._units.get(unit_id)
        if unit is None:
            raise CorpusError(f"Unknown reading unit id: {unit_id}")
        raw = unit.path.read_text(encoding="utf-8")
        _, body = self._split_frontmatter(raw, unit.path)
        return ReadingUnitDocument(meta=unit, body=body.strip())

    def list_chapters(self) -> list[ReadingUnit]:
        """Compatibility alias: returns reading units, not whole chapters."""
        return self.list_units()

    def get_chapter(self, chapter_id: str) -> ReadingUnitDocument:
        """Compatibility alias: accepts a reading unit id."""
        return self.get_unit(chapter_id)

    def refresh(self) -> None:
        self._units = self._scan()

    def _ensure_loaded(self) -> None:
        if self._units is None:
            self.refresh()

    def _scan(self) -> dict[str, ReadingUnit]:
        if not self.corpus_dir.exists():
            return {}
        units: dict[str, ReadingUnit] = {}
        for path in self._iter_markdown_files():
            raw = path.read_text(encoding="utf-8")
            frontmatter, _ = self._split_frontmatter(raw, path)
            unit = self._unit_from_frontmatter(frontmatter, path)
            if unit.id in units:
                raise CorpusError(f"Duplicate reading unit id: {unit.id}")
            units[unit.id] = unit
        return units

    def _iter_markdown_files(self) -> Iterable[Path]:
        root = self.corpus_dir
        for path in root.rglob("*.md"):
            resolved = path.resolve()
            if not resolved.is_relative_to(root):
                raise CorpusError(f"Path escapes corpus root: {path}")
            if path.name.lower() == "readme.md":
                continue
            yield resolved

    @staticmethod
    def _split_frontmatter(raw: str, path: Path) -> tuple[dict, str]:
        if not raw.startswith("---"):
            raise CorpusError(f"Missing YAML frontmatter: {path}")
        parts = raw.split("---", 2)
        if len(parts) < 3:
            raise CorpusError(f"Malformed YAML frontmatter: {path}")
        data = yaml.safe_load(parts[1]) or {}
        if not isinstance(data, dict):
            raise CorpusError(f"Frontmatter must be a mapping: {path}")
        return data, parts[2]

    @staticmethod
    def _unit_from_frontmatter(data: dict, path: Path) -> ReadingUnit:
        required = [
            "id",
            "book_id",
            "book_title",
            "chapter_no",
            "chapter_title",
        ]
        missing = [key for key in required if key not in data]
        if missing:
            raise CorpusError(f"Missing frontmatter keys {missing}: {path}")

        unit_id = str(data["id"])
        chapter_id = str(data.get("chapter_id") or _derive_chapter_id(unit_id))
        section_no = int(data.get("section_no") or 1)
        section_count = int(data.get("section_count") or 1)
        summary = str(data.get("summary") or data.get("summary_zh") or "")

        return ReadingUnit(
            id=unit_id,
            chapter_id=chapter_id,
            book_id=str(data["book_id"]),
            book_title=str(data["book_title"]),
            chapter_no=int(data["chapter_no"]),
            chapter_title=str(data["chapter_title"]),
            section_no=section_no,
            section_count=section_count,
            summary=summary,
            path=path,
        )


def _derive_chapter_id(unit_id: str) -> str:
    marker = "-sec"
    if marker in unit_id:
        return unit_id.split(marker, 1)[0]
    return unit_id