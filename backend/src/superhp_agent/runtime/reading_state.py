"""State aggregation for deterministic guided reading cards."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from superhp_agent.corpus import CorpusStore, ReadingUnit
from superhp_agent.memory import ReadingMemoryStore
from superhp_agent.storage import AppDB


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
        )

    @classmethod
    def from_chapter(cls, unit: ReadingUnit, **kwargs: object) -> ReadingUnitState:
        """Compatibility constructor for older tests/imports."""
        return cls.from_unit(unit, **kwargs)


ChapterState = ReadingUnitState


class ReadingStateReader:
    """Build reading-unit states from corpus files, memory, DB, and local artifacts."""

    def __init__(
        self,
        corpus: CorpusStore,
        annotated_dir: str | Path,
        memory_store: ReadingMemoryStore | None = None,
        db: AppDB | None = None,
    ):
        self.corpus = corpus
        self.annotated_dir = Path(annotated_dir)
        self.memory_store = memory_store
        self.db = db

    def list_states(self) -> list[ReadingUnitState]:
        """Build an ordered state list without mutating progress or files."""
        units = self.corpus.list_units()
        next_by_id = self._next_unit_ids(units)
        memory = self.memory_store.load() if self.memory_store else None
        read_ids = set(memory.read_unit_ids) if memory else set()
        annotated_ids = set(memory.annotated_unit_ids) if memory else set()

        return [
            ReadingUnitState.from_unit(
                unit,
                has_annotated_copy=(unit.id in annotated_ids) or self._has_annotated_copy(unit.id),
                is_read=unit.id in read_ids,
                vocab_count=self._vocab_count(unit.id),
                next_unit_id=next_by_id.get(unit.id),
            )
            for unit in units
        ]

    def get_state(self, unit_id: str) -> ReadingUnitState | None:
        for state in self.list_states():
            if state.id == unit_id:
                return state
        return None

    def current_state(self) -> ReadingUnitState | None:
        """Return the last opened unit, if memory has one."""
        if self.memory_store is None:
            return None
        current_unit_id = self.memory_store.load().current_unit_id
        if not current_unit_id:
            return None
        return self.get_state(current_unit_id)

    def first_state(self) -> ReadingUnitState | None:
        states = self.list_states()
        return states[0] if states else None

    def _has_annotated_copy(self, unit_id: str) -> bool:
        return (self.annotated_dir / f"{unit_id}.annotated.md").exists()

    def _vocab_count(self, unit_id: str) -> int:
        if self.db is None:
            return 0
        return self.db.count_vocabulary_for_unit(unit_id)

    @staticmethod
    def _next_unit_ids(units: list[ReadingUnit]) -> dict[str, str]:
        ordered = sorted(units, key=lambda item: (item.book_id, item.chapter_no, item.section_no, item.id))
        result: dict[str, str] = {}
        for idx, unit in enumerate(ordered[:-1]):
            result[unit.id] = ordered[idx + 1].id
        return result