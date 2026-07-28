"""Build the trusted completed-chapter boundary used by Agent tools.

The builder intersects immutable chapter checkpoints with current Corpus
metadata. It does not search text, expose file paths, execute a tool call, or
infer completion from generated annotations.
"""

from __future__ import annotations

from collections import defaultdict

from superhp_agent.contracts import (
    CompletedChapterScope,
    PreviousReadingScope,
)
from superhp_agent.corpus import CorpusStore, ReadingUnit
from superhp_agent.ports.repositories import (
    ChapterReadingCheckpointRepository,
)


class PreviousReadingScopeBuilder:
    """Create a spoiler-safe scope for one currently open reading unit."""

    def __init__(
        self,
        corpus: CorpusStore,
        checkpoint_repository: ChapterReadingCheckpointRepository,
    ):
        self.corpus = corpus
        self.checkpoint_repository = checkpoint_repository

    def build(self, current_unit_id: str) -> PreviousReadingScope:
        """Return only prior chapters confirmed by both checkpoints and Corpus."""
        current_unit_id = str(current_unit_id or "").strip()
        if not current_unit_id:
            raise ValueError("current_unit_id is required")

        units = tuple(self.corpus.list_units())
        current = next(
            (unit for unit in units if unit.id == current_unit_id),
            None,
        )
        if current is None:
            raise ValueError(f"Unknown current reading unit id: {current_unit_id}")

        chapters = _group_book_chapters(units, current.book_id)
        completed_by_id: dict[str, CompletedChapterScope] = {}
        for checkpoint in self.checkpoint_repository.list_for_book(
            current.book_id
        ):
            if (
                checkpoint.book_id != current.book_id
                or checkpoint.chapter_no >= current.chapter_no
            ):
                continue

            chapter_units = chapters.get(checkpoint.chapter_id, ())
            canonical_unit_ids = tuple(unit.id for unit in chapter_units)
            checkpoint_unit_ids = checkpoint.unit_ids
            if (
                not chapter_units
                or any(
                    unit.chapter_no != checkpoint.chapter_no
                    for unit in chapter_units
                )
                or len(set(checkpoint_unit_ids)) != len(checkpoint_unit_ids)
                or set(checkpoint_unit_ids) != set(canonical_unit_ids)
            ):
                continue

            completed_by_id[checkpoint.chapter_id] = CompletedChapterScope(
                chapter_id=checkpoint.chapter_id,
                chapter_no=checkpoint.chapter_no,
                unit_ids=canonical_unit_ids,
            )

        completed_chapters = tuple(
            sorted(
                completed_by_id.values(),
                key=lambda chapter: (chapter.chapter_no, chapter.chapter_id),
            )
        )
        return PreviousReadingScope(
            book_id=current.book_id,
            current_chapter_id=current.chapter_id,
            current_chapter_no=current.chapter_no,
            completed_chapters=completed_chapters,
        )


def _group_book_chapters(
    units: tuple[ReadingUnit, ...],
    book_id: str,
) -> dict[str, tuple[ReadingUnit, ...]]:
    """Group one book's units in canonical section order."""
    grouped: defaultdict[str, list[ReadingUnit]] = defaultdict(list)
    for unit in units:
        if unit.book_id == book_id:
            grouped[unit.chapter_id].append(unit)
    return {
        chapter_id: tuple(
            sorted(
                chapter_units,
                key=lambda unit: (unit.section_no, unit.id),
            )
        )
        for chapter_id, chapter_units in grouped.items()
    }
