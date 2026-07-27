"""Persistence boundary for generated annotated reading copies.

This store owns annotated-copy filenames, Markdown
serialization, and filesystem reads/writes. Runtime handlers decide when an
artifact should be generated or opened; this module does not route actions,
call models, update reading progress, or emit transport events.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from superhp_agent.corpus import ReadingUnitDocument
from superhp_agent.domain.reading_support import validate_annotation_target

ANNOTATION_FORMAT_VERSION = 1
VALID_ANNOTATION_STATUSES = {"completed", "degraded"}


@dataclass(frozen=True)
class AnnotatedCopy:
    """One persisted annotated copy resolved for reading."""

    path: Path
    metadata: str
    body: str

    @property
    def annotation_target(self) -> int | None:
        """Return the generation target recorded in frontmatter, when present."""
        parsed = yaml.safe_load(self.metadata) or {}
        if not isinstance(parsed, dict):
            raise ValueError("annotated copy metadata must be a mapping")
        raw_target = parsed.get("annotation_target")
        if raw_target is None:
            return None
        return validate_annotation_target(raw_target)


class AnnotatedCopyStore:
    """Read and write one canonical annotated Markdown artifact per unit."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def path_for(self, unit_id: str) -> Path:
        """Return the canonical annotated path without touching disk."""
        self._validate_unit_id(unit_id)
        return self.root / f"{unit_id}.annotated.md"

    def exists_any(self, unit_id: str) -> bool:
        """Return whether the canonical copy exists for one unit."""
        return self.path_for(unit_id).exists()

    def read(self, unit_id: str) -> AnnotatedCopy | None:
        """Read a resolved annotated copy, or return None when it is missing."""
        path = self.path_for(unit_id)
        if not path.exists():
            return None
        metadata, body = self._split_markdown(path.read_text(encoding="utf-8"))
        return AnnotatedCopy(path=path, metadata=metadata, body=body.strip())

    def write(
        self,
        document: ReadingUnitDocument,
        *,
        annotated_text: str,
        vocabulary: Iterable[Any],
        status: str = "completed",
        validated_chunk_count: int = 1,
        total_chunk_count: int = 1,
        annotation_target: int | None = None,
    ) -> Path:
        """Atomically persist one canonical annotated copy."""
        if status not in VALID_ANNOTATION_STATUSES:
            raise ValueError(f"Invalid annotation status: {status!r}")
        validated_chunk_count = int(validated_chunk_count)
        total_chunk_count = int(total_chunk_count)
        if not 0 <= validated_chunk_count <= total_chunk_count:
            raise ValueError("validated_chunk_count must be between 0 and total_chunk_count")
        if annotation_target is not None:
            annotation_target = validate_annotation_target(annotation_target)
        path = self.path_for(document.meta.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        rendered = self._render_markdown(
            document,
            annotated_text=annotated_text,
            vocabulary=vocabulary,
            status=status,
            validated_chunk_count=validated_chunk_count,
            total_chunk_count=total_chunk_count,
            annotation_target=annotation_target,
        )
        self._atomic_write(path, rendered)
        return path

    @staticmethod
    def _render_markdown(
        document: ReadingUnitDocument,
        *,
        annotated_text: str,
        vocabulary: Iterable[Any],
        status: str,
        validated_chunk_count: int,
        total_chunk_count: int,
        annotation_target: int | None,
    ) -> str:
        vocab_lines = "\n".join(
            f"# - {item.word}: {item.translation} ({getattr(item, 'pos', 'other')})"
            for item in vocabulary
            if item.word or item.translation
        )
        annotated_at = datetime.now(UTC).isoformat()
        source_hash = hashlib.sha256(document.body.encode("utf-8")).hexdigest()
        annotation_target_line = (
            f"annotation_target: {annotation_target}\n"
            if annotation_target is not None
            else ""
        )
        return (
            "---\n"
            f"source_unit_id: {document.meta.id}\n"
            f"chapter_id: {document.meta.chapter_id}\n"
            f"book_id: {document.meta.book_id}\n"
            f"chapter_no: {document.meta.chapter_no}\n"
            f"profile_id: {document.meta.profile_id}\n"
            "body_kind: annotated\n"
            f"source_hash: {source_hash}\n"
            f"annotation_format_version: {ANNOTATION_FORMAT_VERSION}\n"
            f"status: {status}\n"
            f"validated_chunk_count: {validated_chunk_count}\n"
            f"total_chunk_count: {total_chunk_count}\n"
            f"{annotation_target_line}"
            f"annotated_at: {annotated_at}\n"
            "---\n\n"
            f"<!-- extracted_vocabulary\n{vocab_lines}\n-->\n\n"
            f"{annotated_text.strip()}\n"
        )

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        """Replace the target only after a complete same-directory write."""
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            temp_path.replace(path)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

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
