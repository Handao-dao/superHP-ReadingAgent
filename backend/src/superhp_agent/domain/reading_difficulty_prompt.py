"""Persistent user-consent state for book-difficulty prompts.

This state is deliberately separate from annotation-target cooldowns. It
records what the reader saw and chose; it does not calculate reading density,
run an Agent, or change the active book.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from superhp_agent.contracts import ReadingDifficultyEvidence

DIFFICULTY_PROMPT_COOLDOWN_CHAPTERS = 3


class ReadingDifficultyPromptStatus(StrEnum):
    """Current lifecycle state for one book's latest prompt."""

    PENDING = "pending"
    CONTINUE_READING = "continue_reading"
    CHANGE_BOOK = "change_book"


@dataclass(frozen=True)
class ReadingDifficultyPrompt:
    """Latest prompt, its evidence, and any explicit reader response."""

    book_id: str
    chapter_id: str
    status: ReadingDifficultyPromptStatus
    evidence: ReadingDifficultyEvidence
    cooldown_chapters_remaining: int = 0
    last_cooldown_chapter_id: str = ""
    recommendation_session_id: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not self.book_id.strip():
            raise ValueError("book_id must not be empty")
        if not self.chapter_id.strip():
            raise ValueError("chapter_id must not be empty")
        if self.cooldown_chapters_remaining < 0:
            raise ValueError(
                "difficulty prompt cooldown must not be negative"
            )
        if (
            self.status is ReadingDifficultyPromptStatus.PENDING
            and self.cooldown_chapters_remaining
        ):
            raise ValueError("pending difficulty prompt cannot be cooling down")
        if (
            self.status is ReadingDifficultyPromptStatus.CHANGE_BOOK
            and not self.recommendation_session_id.strip()
        ):
            raise ValueError(
                "change_book prompt requires a recommendation session"
            )
