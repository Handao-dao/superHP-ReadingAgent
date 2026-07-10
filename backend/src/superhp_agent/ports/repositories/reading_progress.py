"""Minimal persistence capability for single-user reading progress."""

from typing import Protocol, runtime_checkable

from superhp_agent.contracts.reading import ReadingProgressSnapshot


@runtime_checkable
class ReadingProgressRepository(Protocol):
    """Read and update the current, opened, and completed reading units."""

    def load(self) -> ReadingProgressSnapshot: ...

    def mark_opened(self, unit_id: str) -> ReadingProgressSnapshot: ...

    def mark_read(self, unit_id: str) -> ReadingProgressSnapshot: ...
