"""Persistence capability for per-book difficulty prompt state."""

from typing import Protocol, runtime_checkable

from superhp_agent.contracts import ReadingDifficultyEvidence
from superhp_agent.domain.reading_difficulty_prompt import (
    ReadingDifficultyPrompt,
)


@runtime_checkable
class ReadingDifficultyPromptRepository(Protocol):
    """Persist, resolve, and advance the latest prompt for one book."""

    def get(self, book_id: str) -> ReadingDifficultyPrompt | None: ...

    def open_prompt(
        self,
        *,
        book_id: str,
        chapter_id: str,
        evidence: ReadingDifficultyEvidence,
    ) -> ReadingDifficultyPrompt: ...

    def choose_continue(
        self,
        book_id: str,
        *,
        cooldown_chapters: int,
    ) -> ReadingDifficultyPrompt: ...

    def choose_change_book(
        self,
        book_id: str,
        *,
        recommendation_session_id: str,
    ) -> ReadingDifficultyPrompt: ...

    def advance_cooldown(
        self,
        book_id: str,
        *,
        chapter_id: str,
    ) -> ReadingDifficultyPrompt | None: ...
