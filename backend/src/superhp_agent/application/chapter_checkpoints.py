"""Record one immutable observation when an English chapter fully completes.

The recorder derives a chapter from Corpus metadata, checks completion through
the progress Port, snapshots lookup facts, and delegates persistence. It does
not evaluate adaptation policy or change the current annotation target.
"""

from __future__ import annotations

from superhp_agent.artifacts import AnnotatedCopyStore
from superhp_agent.contracts import ChapterReadingCheckpoint
from superhp_agent.corpus import CorpusStore, ReadingUnit
from superhp_agent.domain.reading_metrics import count_english_words
from superhp_agent.ports.repositories import (
    ChapterReadingCheckpointRepository,
    ReadingLookupRepository,
    ReadingProgressRepository,
)


class ChapterCheckpointRecorder:
    """Create a checkpoint only after every unit in one chapter is read."""

    def __init__(
        self,
        corpus: CorpusStore,
        progress_repository: ReadingProgressRepository,
        lookup_repository: ReadingLookupRepository,
        checkpoint_repository: ChapterReadingCheckpointRepository,
        annotated_copies: AnnotatedCopyStore,
    ):
        self.corpus = corpus
        self.progress_repository = progress_repository
        self.lookup_repository = lookup_repository
        self.checkpoint_repository = checkpoint_repository
        self.annotated_copies = annotated_copies

    def record_if_complete(
        self,
        unit_id: str,
    ) -> ChapterReadingCheckpoint | None:
        """Record the chapter containing ``unit_id`` once it is fully read."""
        completed_unit = self.corpus.get_unit(unit_id).meta
        if completed_unit.language_id != "en":
            return None

        chapter_units = tuple(
            sorted(
                (
                    unit
                    for unit in self.corpus.list_units()
                    if unit.book_id == completed_unit.book_id
                    and unit.chapter_id == completed_unit.chapter_id
                ),
                key=lambda unit: (unit.section_no, unit.id),
            )
        )
        read_unit_ids = set(self.progress_repository.load().read_unit_ids)
        unit_ids = tuple(unit.id for unit in chapter_units)
        if not unit_ids or not set(unit_ids).issubset(read_unit_ids):
            return None

        documents = tuple(self.corpus.get_unit(unit.id) for unit in chapter_units)
        lookup_summary = self.lookup_repository.summarize_lookups(
            unit_ids=unit_ids,
        )
        checkpoint = ChapterReadingCheckpoint(
            book_id=completed_unit.book_id,
            chapter_id=completed_unit.chapter_id,
            chapter_no=completed_unit.chapter_no,
            unit_ids=unit_ids,
            word_count=sum(
                count_english_words(document.body) for document in documents
            ),
            lookup_count=lookup_summary.lookup_count,
            annotated_lookup_count=lookup_summary.annotated_lookup_count,
            annotation_target=self._shared_annotation_target(chapter_units),
        )
        return self.checkpoint_repository.record(checkpoint)

    def _shared_annotation_target(
        self,
        chapter_units: tuple[ReadingUnit, ...],
    ) -> int | None:
        """Return one actual target only when every unit has the same value."""
        targets: list[int] = []
        for unit in chapter_units:
            annotated_copy = self.annotated_copies.read(unit.id)
            if annotated_copy is None:
                return None
            annotation_target = annotated_copy.annotation_target
            if annotation_target is None:
                return None
            targets.append(annotation_target)
        unique_targets = set(targets)
        return targets[0] if len(unique_targets) == 1 else None
