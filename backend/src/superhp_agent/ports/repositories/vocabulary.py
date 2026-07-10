"""Minimal vocabulary persistence capability required by guided reading.

The port exposes only the operations currently used by Runtime and read-state
aggregation. It does not prescribe SQLite tables, transactions, migrations,
HTTP DTOs, or bookmark persistence.
"""

from typing import Any, Protocol, runtime_checkable

from superhp_agent.corpus import ReadingUnit


@runtime_checkable
class VocabularyRepository(Protocol):
    """Vocabulary reads and writes required by the guided-reading workflow."""

    def list_mastered_words(self) -> list[str]: ...

    def add_vocabulary_items(self, unit: ReadingUnit, items: list[Any]) -> int: ...

    def count_vocabulary_for_unit(self, unit_id: str) -> int: ...
