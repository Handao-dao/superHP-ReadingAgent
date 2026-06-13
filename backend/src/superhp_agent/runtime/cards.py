"""Deterministic guided-card templates for the reading flow."""

from __future__ import annotations

from superhp_agent.profiles import CardCopy
from superhp_agent.runtime.actions import (
    GENERATE_ANNOTATION,
    OPEN_ANNOTATED_COPY,
    READ_ORIGINAL,
    REVIEW_CHAPTER_VOCAB,
    START_NEXT_CHAPTER,
    action,
)
from superhp_agent.runtime.reading_state import ReadingUnitState
from superhp_agent.schemas import AgentCard


class ReadingCardBuilder:
    """Build small, choice-based cards for the constrained reading UI.

    Keeping copy and action ids here makes it easier to refine the UX without
    touching WebSocket transport or action execution code.
    """
    def __init__(self, card_copy: CardCopy | None = None):
        self.copy = card_copy or CardCopy()

    def empty_corpus(self) -> list[AgentCard]:
        return [
            AgentCard(
                id="empty-corpus",
                type="setup",
                title=self.copy.empty_title,
                body=self.copy.empty_body,
                actions=[],
            )
        ]

    def start_reading(self, unit: ReadingUnitState) -> list[AgentCard]:
        return self.start_unit(unit)

    def start_unit(self, unit: ReadingUnitState) -> list[AgentCard]:
        actions = []
        if unit.has_annotated_copy:
            actions.append(action(OPEN_ANNOTATED_COPY, chapter_id=unit.id, unit_id=unit.id))
        else:
            actions.append(action(GENERATE_ANNOTATION, chapter_id=unit.id, unit_id=unit.id))
        actions.append(action(READ_ORIGINAL, chapter_id=unit.id, unit_id=unit.id))
        if unit.has_annotated_copy and unit.vocab_count > 0:
            actions.append(action(REVIEW_CHAPTER_VOCAB, chapter_id=unit.id, unit_id=unit.id))

        return [
            AgentCard(
                id=f"unit-{unit.id}-start",
                type="reading",
                title=self.copy.start_title,
                body=self._unit_title(unit, self.copy.start_prefix),
                actions=actions,
            )
        ]

    def complete_unit(self, unit: ReadingUnitState) -> list[AgentCard]:
        actions = []
        if unit.next_unit_id:
            actions.append(
                action(
                    START_NEXT_CHAPTER,
                    chapter_id=unit.next_unit_id,
                    unit_id=unit.next_unit_id,
                    completed_unit_id=unit.id,
                )
            )
        if unit.vocab_count > 0:
            actions.append(action(REVIEW_CHAPTER_VOCAB, chapter_id=unit.id, unit_id=unit.id))
        if unit.has_annotated_copy:
            back_action = action(OPEN_ANNOTATED_COPY, chapter_id=unit.id, unit_id=unit.id)
            back_action.label = self.copy.back_to_annotated_label
            actions.append(back_action)
        else:
            back_action = action(READ_ORIGINAL, chapter_id=unit.id, unit_id=unit.id)
            back_action.label = self.copy.back_to_source_label
            actions.append(back_action)

        title = self.copy.complete_title if unit.next_unit_id else self.copy.final_complete_title
        return [
            AgentCard(
                id=f"unit-{unit.id}-complete",
                type="progress",
                title=title,
                body=self._vocab_body(unit, self.copy.complete_prefix),
                actions=actions,
            )
        ]

    def chapter_cards(self, unit: ReadingUnitState) -> list[AgentCard]:
        return self.unit_cards(unit)

    def unit_cards(self, unit: ReadingUnitState) -> list[AgentCard]:
        """Select the card variant from the user's progress on one unit."""
        return self.start_unit(unit)

    @staticmethod
    def _unit_title(unit: ReadingUnitState, prefix: str) -> str:
        return (
            f"{prefix}: {unit.book_title}, Chapter {unit.chapter_no}, "
            f"{unit.chapter_title}."
        )

    def _vocab_body(self, unit: ReadingUnitState, prefix: str) -> str:
        if unit.vocab_count <= 0:
            return prefix
        word_label = self.copy.learning_item_singular if unit.vocab_count == 1 else self.copy.learning_item_plural
        return f"{prefix} This chapter currently has {unit.vocab_count} {self.copy.learning_item_scope} {word_label}."
