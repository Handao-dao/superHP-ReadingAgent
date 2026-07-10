"""Persistence boundary for generated annotated reading copies.

This store owns annotated-copy filenames, legacy fallback, Markdown
serialization, and filesystem reads/writes. Runtime handlers decide when an
artifact should be generated or opened; this module does not route actions,
call models, update reading progress, or emit transport events.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from superhp_agent.corpus import ReadingUnitDocument


@dataclass(frozen=True)
class AnnotatedCopy:
    """One persisted annotated copy resolved for reading."""

    path: Path
    metadata: str
    body: str


class AnnotatedCopyStore:
    """Read and write level-specific annotated Markdown artifacts."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def path_for(self, unit_id: str, level: str) -> Path:
        """Return the canonical density-specific path without touching disk."""
        self._validate_unit_id(unit_id)
        return self.root / f"{unit_id}.{level}.annotated.md"

    def legacy_path_for(self, unit_id: str) -> Path:
        """Return the pre-density annotated path used by older versions."""
        self._validate_unit_id(unit_id)
        return self.root / f"{unit_id}.annotated.md"

    def exists_any(self, unit_id: str) -> bool:
        """Return whether any density or legacy copy exists for one unit."""
        legacy_path = self.legacy_path_for(unit_id)
        return legacy_path.exists() or any(self.root.glob(f"{unit_id}.*.annotated.md"))

    def find_path(self, unit_id: str, level: str) -> Path | None:
        """Resolve an exact copy, with legacy fallback for intermediate only."""
        annotated_path = self.path_for(unit_id, level)
        if annotated_path.exists():
            return annotated_path
        if level == "intermediate":
            legacy_path = self.legacy_path_for(unit_id)
            if legacy_path.exists():
                return legacy_path
        return None

    def read(self, unit_id: str, level: str) -> AnnotatedCopy | None:
        """Read a resolved annotated copy, or return None when it is missing."""
        path = self.find_path(unit_id, level)
        if path is None:
            return None
        metadata, body = self._split_markdown(path.read_text(encoding="utf-8"))
        return AnnotatedCopy(path=path, metadata=metadata, body=body.strip())

    def write(
        self,
        document: ReadingUnitDocument,
        *,
        annotated_text: str,
        vocabulary: Iterable[Any],
        level: str,
    ) -> Path:
        """Serialize and persist one canonical density-specific copy."""
        path = self.path_for(document.meta.id, level)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            self._render_markdown(
                document,
                annotated_text=annotated_text,
                vocabulary=vocabulary,
                level=level,
            ),
            encoding="utf-8",
        )
        return path

    @staticmethod
    def _render_markdown(
        document: ReadingUnitDocument,
        *,
        annotated_text: str,
        vocabulary: Iterable[Any],
        level: str,
    ) -> str:
        vocab_lines = "\n".join(
            f"# - {item.word}: {item.translation} ({getattr(item, 'pos', 'other')})"
            for item in vocabulary
            if item.word or item.translation
        )
        annotated_at = datetime.now(UTC).isoformat()
        return (
            "---\n"
            f"source_unit_id: {document.meta.id}\n"
            f"chapter_id: {document.meta.chapter_id}\n"
            f"book_id: {document.meta.book_id}\n"
            f"chapter_no: {document.meta.chapter_no}\n"
            f"profile_id: {document.meta.profile_id}\n"
            f"level: {level}\n"
            "body_kind: annotated\n"
            f"annotated_at: {annotated_at}\n"
            "---\n\n"
            f"<!-- extracted_vocabulary\n{vocab_lines}\n-->\n\n"
            f"{annotated_text.strip()}\n"
        )

    @staticmethod
    def _split_markdown(raw: str) -> tuple[str, str]:
        if not raw.startswith("---"):
            return "", raw
        parts = raw.split("---", 2)
        if len(parts) < 3:
            return "", raw
        return parts[1], parts[2]

    @staticmethod
    def _validate_unit_id(unit_id: str) -> None:
        if not unit_id or Path(unit_id).name != unit_id or unit_id in {".", ".."}:
            raise ValueError(f"Invalid reading unit id: {unit_id!r}")
