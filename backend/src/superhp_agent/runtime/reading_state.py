"""State aggregation for deterministic guided reading cards."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from superhp_agent.artifacts import AnnotatedCopyStore
from superhp_agent.corpus import CorpusStore, ReadingUnit
from superhp_agent.ports.repositories import (
    ReadingProgressRepository,
    VocabularyRepository,
)


@dataclass(frozen=True)
class ReadingUnitState:
    """Frontend-ready snapshot assembled from corpus, memory, and artifacts."""
    id: str
    chapter_id: str
    book_id: str
    book_title: str
    chapter_no: int
    chapter_title: str
    section_no: int = 1
    section_count: int = 1
    summary: str = ""
    has_annotated_copy: bool = False
    is_read: bool = False
    vocab_count: int = 0
    next_unit_id: str | None = None
    profile_id: str = "english_novel"

    @property
    def summary_zh(self) -> str:
        return self.summary

    @property
    def next_chapter_id(self) -> str | None:
        """Compatibility alias for older action payload naming."""
        return self.next_unit_id

    @classmethod
    def from_unit(
        cls,
        unit: ReadingUnit,
        *,
        has_annotated_copy: bool = False,
        is_read: bool = False,
        vocab_count: int = 0,
        next_unit_id: str | None = None,
    ) -> ReadingUnitState:
        return cls(
            id=unit.id,
            chapter_id=unit.chapter_id,
            book_id=unit.book_id,
            book_title=unit.book_title,
            chapter_no=unit.chapter_no,
            chapter_title=unit.chapter_title,
            section_no=unit.section_no,
            section_count=unit.section_count,
            summary=unit.summary,
            has_annotated_copy=has_annotated_copy,
            is_read=is_read,
            vocab_count=vocab_count,
            next_unit_id=next_unit_id,
            profile_id=unit.profile_id,
        )

    @classmethod
    def from_chapter(cls, unit: ReadingUnit, **kwargs: object) -> ReadingUnitState:
        """Compatibility constructor for older tests/imports."""
        return cls.from_unit(unit, **kwargs)


ChapterState = ReadingUnitState


class ReadingStateReader:
    """Build unit states from corpus, progress/vocabulary repositories, and artifacts."""

    def __init__(
        self,
        corpus: CorpusStore,
        annotated_copies: AnnotatedCopyStore | str | Path,
        progress_repository: ReadingProgressRepository | None = None,
        db: VocabularyRepository | None = None,
    ):
        self.corpus = corpus
        self.annotated_copies = (
            annotated_copies
            if isinstance(annotated_copies, AnnotatedCopyStore)
            else AnnotatedCopyStore(annotated_copies)
        )
        self.progress_repository = progress_repository
        self.db = db

    def list_states(self, profile_id: str | None = None) -> list[ReadingUnitState]:
        """Build an ordered state list without mutating progress or files."""
        units = self.corpus.list_units()
        if profile_id:
            units = [unit for unit in units if unit.profile_id == profile_id]
        next_by_id = self._next_unit_ids(units)
        progress = self.progress_repository.load() if self.progress_repository else None
        read_ids = set(progress.read_unit_ids) if progress else set()

        return [
            ReadingUnitState.from_unit(
                unit,
                has_annotated_copy=self._has_annotated_copy(unit.id),
                is_read=unit.id in read_ids,
                vocab_count=self._vocab_count(unit.id),
                next_unit_id=next_by_id.get(unit.id),
            )
            for unit in units
        ]

    def get_state(self, unit_id: str, *, profile_id: str | None = None) -> ReadingUnitState | None:
        for state in self.list_states(profile_id=profile_id):
            if state.id == unit_id:
                return state
        return None

    def current_state(self, *, profile_id: str | None = None) -> ReadingUnitState | None:
        """Return the last opened unit, if memory has one."""
        if self.progress_repository is None:
            return None
        current_unit_id = self.progress_repository.load().current_unit_id
        if not current_unit_id:
            return None
        return self.get_state(current_unit_id, profile_id=profile_id)

    def first_state(self, *, profile_id: str | None = None) -> ReadingUnitState | None:
        states = self.list_states(profile_id=profile_id)
        return states[0] if states else None

    def _has_annotated_copy(self, unit_id: str) -> bool:
        return self.annotated_copies.exists_any(unit_id)

    def _vocab_count(self, unit_id: str) -> int:
        if self.db is None:
            return 0
        return self.db.count_vocabulary_for_unit(unit_id)

    @staticmethod
    def _next_unit_ids(units: list[ReadingUnit]) -> dict[str, str]:
        ordered = sorted(units, key=lambda item: (item.book_id, item.chapter_no, item.id))
        result: dict[str, str] = {}
        for idx, unit in enumerate(ordered[:-1]):
            result[unit.id] = ordered[idx + 1].id
        return result
