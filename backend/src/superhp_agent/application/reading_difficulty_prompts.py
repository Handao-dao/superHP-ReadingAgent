"""Coordinate persisted difficulty prompts with annotation-support state."""

from __future__ import annotations

from dataclasses import replace

from superhp_agent.domain.reading_difficulty_prompt import (
    DIFFICULTY_PROMPT_COOLDOWN_CHAPTERS,
    ReadingDifficultyPrompt,
    ReadingDifficultyPromptStatus,
)
from superhp_agent.ports import (
    ReadingDifficultyPromptRepository,
    ReadingSupportRepository,
)


class ReadingDifficultyPromptCoordinator:
    """Apply explicit reader choices without owning policy evaluation."""

    def __init__(
        self,
        prompt_repository: ReadingDifficultyPromptRepository,
        support_repository: ReadingSupportRepository,
    ):
        self.prompt_repository = prompt_repository
        self.support_repository = support_repository

    def require_pending(self, book_id: str) -> ReadingDifficultyPrompt:
        prompt = self.prompt_repository.get(book_id)
        if (
            prompt is None
            or prompt.status is not ReadingDifficultyPromptStatus.PENDING
        ):
            raise ValueError("difficulty prompt is not awaiting a choice")
        return prompt

    def choose_continue(self, book_id: str) -> ReadingDifficultyPrompt:
        """Record consent to continue and begin a three-chapter cooldown."""
        prompt = self.prompt_repository.choose_continue(
            book_id,
            cooldown_chapters=DIFFICULTY_PROMPT_COOLDOWN_CHAPTERS,
        )
        self._reset_alert_confirmation(
            book_id,
            last_decision="difficulty_prompt:continue_reading",
        )
        return prompt

    def choose_change_book(
        self,
        book_id: str,
        *,
        recommendation_session_id: str,
    ) -> ReadingDifficultyPrompt:
        """Link an authorized book-change choice to its Agent session."""
        prompt = self.prompt_repository.choose_change_book(
            book_id,
            recommendation_session_id=recommendation_session_id,
        )
        self._reset_alert_confirmation(
            book_id,
            last_decision="difficulty_prompt:change_book",
        )
        return prompt

    def _reset_alert_confirmation(
        self,
        book_id: str,
        *,
        last_decision: str,
    ) -> None:
        current = self.support_repository.get_state(book_id)
        self.support_repository.save_evaluation_state(
            book_id,
            replace(
                current,
                max_target_high_density_streak=0,
                last_decision=last_decision,
            ),
        )
