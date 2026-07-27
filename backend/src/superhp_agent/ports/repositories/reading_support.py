"""Persistence capability for per-book English annotation support state.

The repository stores the current target only. It does not inspect reading
behavior, decide when to adjust the target, or regenerate annotated copies.
"""

from typing import Protocol, runtime_checkable

from superhp_agent.domain.reading_support import ReadingSupportState


@runtime_checkable
class ReadingSupportRepository(Protocol):
    """Read and update the current annotation target for one book."""

    def get_annotation_target(self, book_id: str) -> int: ...

    def set_annotation_target(self, book_id: str, annotation_target: int) -> None: ...

    def get_state(self, book_id: str) -> ReadingSupportState: ...

    def save_evaluation_state(
        self,
        book_id: str,
        state: ReadingSupportState,
    ) -> None: ...
