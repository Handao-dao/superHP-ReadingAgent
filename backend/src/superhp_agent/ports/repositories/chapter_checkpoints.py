"""Persistence capability for immutable completed-chapter observations."""

from typing import Protocol, runtime_checkable

from superhp_agent.contracts import ChapterReadingCheckpoint


@runtime_checkable
class ChapterReadingCheckpointRepository(Protocol):
    """Record each completed chapter once and return stored checkpoints."""

    def record(
        self,
        checkpoint: ChapterReadingCheckpoint,
    ) -> ChapterReadingCheckpoint | None: ...

    def list_for_book(self, book_id: str) -> tuple[ChapterReadingCheckpoint, ...]: ...
