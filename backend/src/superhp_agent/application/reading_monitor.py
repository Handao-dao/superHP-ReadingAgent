"""Build deterministic, read-only observations of English reading difficulty.

The monitor aggregates completed reading units and persisted lookup facts. It
does not alter annotation prompts, display a difficulty alert, apply cooldowns,
or start the recommendation Agent. Those decisions remain explicit later
application steps.
"""

from __future__ import annotations

from dataclasses import dataclass

from superhp_agent.contracts import (
    ReadingDifficultyEvidence,
    ReadingDifficultyObservation,
    ReadingDifficultyState,
)
from superhp_agent.corpus import CorpusStore, ReadingUnitDocument
from superhp_agent.domain.reading_metrics import count_english_words
from superhp_agent.ports.repositories import (
    ReadingLookupRepository,
    ReadingProgressRepository,
)


@dataclass(frozen=True)
class ReadingDifficultyPolicy:
    """Configurable product thresholds for the first long-window monitor."""

    minimum_chapters: int = 3
    minimum_words: int = 5000
    watching_lookups_per_300: float = 10.0

    def __post_init__(self) -> None:
        if self.minimum_chapters < 1:
            raise ValueError("minimum_chapters must be positive")
        if self.minimum_words < 1:
            raise ValueError("minimum_words must be positive")
        if self.watching_lookups_per_300 < 0:
            raise ValueError("watching lookup density must not be negative")


class ReadingDifficultyMonitor:
    """Aggregate completed English units into a stable monitoring observation."""

    def __init__(
        self,
        corpus: CorpusStore,
        progress_repository: ReadingProgressRepository,
        lookup_repository: ReadingLookupRepository,
        *,
        policy: ReadingDifficultyPolicy | None = None,
    ):
        self.corpus = corpus
        self.progress_repository = progress_repository
        self.lookup_repository = lookup_repository
        self.policy = policy or ReadingDifficultyPolicy()

    def observe_book(self, book_id: str) -> ReadingDifficultyObservation:
        """Observe all completed English units currently available for one book."""
        book_id = str(book_id or "").strip()
        if not book_id:
            raise ValueError("book_id is required")

        book_units = [
            unit
            for unit in self.corpus.list_units()
            if unit.book_id == book_id and unit.language_id == "en"
        ]
        if not book_units:
            raise ValueError(f"Unknown English book id: {book_id}")

        read_ids = set(self.progress_repository.load().read_unit_ids)
        completed_units = [unit for unit in book_units if unit.id in read_ids]
        documents = [self.corpus.get_unit(unit.id) for unit in completed_units]
        observed_word_count = sum(_english_word_count(doc) for doc in documents)
        observed_chapter_count = len(
            {document.meta.chapter_id for document in documents}
        )
        unit_ids = tuple(document.meta.id for document in documents)
        lookup_summary = self.lookup_repository.summarize_lookups(
            unit_ids=unit_ids,
        )
        evidence = ReadingDifficultyEvidence(
            observed_word_count=observed_word_count,
            observed_chapter_count=observed_chapter_count,
            lookup_density=_density(
                lookup_summary.lookup_count,
                observed_word_count,
            ),
            unique_lookup_density=_density(
                lookup_summary.unique_lookup_count,
                observed_word_count,
            ),
            repeated_lookup_density=_density(
                lookup_summary.repeated_lookup_count,
                observed_word_count,
            ),
            annotated_lookup_density=_density(
                lookup_summary.annotated_lookup_count,
                observed_word_count,
            ),
        )
        window_ready = (
            observed_chapter_count >= self.policy.minimum_chapters
            and observed_word_count >= self.policy.minimum_words
        )
        state = (
            ReadingDifficultyState.WATCHING
            if window_ready
            and evidence.lookup_density
            > self.policy.watching_lookups_per_300
            else ReadingDifficultyState.NORMAL
        )
        return ReadingDifficultyObservation(
            book_id=book_id,
            state=state,
            evidence=evidence,
            observed_unit_ids=unit_ids,
            window_ready=window_ready,
        )


def _english_word_count(document: ReadingUnitDocument) -> int:
    """Count English words only; punctuation does not affect monitor density."""
    return count_english_words(document.body)


def _density(count: int, observed_word_count: int) -> float:
    if observed_word_count <= 0:
        return 0.0
    return round(count / observed_word_count * 300, 2)
