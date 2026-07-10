"""Deterministic guided-card templates for the reading flow."""

from __future__ import annotations

from superhp_agent.contracts import AgentCard
from superhp_agent.profiles import CardCopy, ProfileRegistry
from superhp_agent.runtime.actions import (
    GENERATE_ANNOTATION,
    OPEN_ANNOTATED_COPY,
    READ_ORIGINAL,
    REVIEW_CHAPTER_VOCAB,
    START_NEXT_CHAPTER,
    action,
)
from superhp_agent.runtime.reading_state import ReadingUnitState


class ReadingCardBuilder:
    """Build small, choice-based cards for the constrained reading UI.

    Keeping copy and action ids here makes it easier to refine the UX without
    touching WebSocket transport or action execution code.
    """
    def __init__(self, card_copy: CardCopy | None = None, *, profile_registry: ProfileRegistry | None = None):
        self.copy = card_copy or CardCopy()
        self.profile_registry = profile_registry

    def empty_corpus(self, profile_id: str | None = None) -> list[AgentCard]:
        copy = self._copy_for_profile(profile_id)
        return [
            AgentCard(
                id="empty-corpus",
                type="setup",
                title=copy.empty_title,
                body=copy.empty_body,
                actions=[],
            )
        ]

    def start_reading(self, unit: ReadingUnitState) -> list[AgentCard]:
        return self.start_unit(unit)

    def start_unit(self, unit: ReadingUnitState) -> list[AgentCard]:
        copy = self._copy_for(unit)
        actions = []
        if unit.has_annotated_copy:
            actions.append(action(OPEN_ANNOTATED_COPY, chapter_id=unit.id, unit_id=unit.id))
            actions[-1].label = copy.open_annotated_label
        else:
            actions.append(action(GENERATE_ANNOTATION, chapter_id=unit.id, unit_id=unit.id))
            actions[-1].label = copy.generate_annotation_label
        actions.append(action(READ_ORIGINAL, chapter_id=unit.id, unit_id=unit.id))
        actions[-1].label = copy.read_original_label
        if unit.has_annotated_copy and unit.vocab_count > 0:
            actions.append(action(REVIEW_CHAPTER_VOCAB, chapter_id=unit.id, unit_id=unit.id))
            actions[-1].label = copy.review_items_label

        return [
            AgentCard(
                id=f"unit-{unit.id}-start",
                type="reading",
                title=copy.start_title,
                body=self._unit_title(unit, copy.start_prefix, copy=copy),
                actions=actions,
            )
        ]

    def complete_unit(self, unit: ReadingUnitState) -> list[AgentCard]:
        copy = self._copy_for(unit)
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
            actions[-1].label = copy.start_next_label
        if unit.vocab_count > 0:
            actions.append(action(REVIEW_CHAPTER_VOCAB, chapter_id=unit.id, unit_id=unit.id))
            actions[-1].label = copy.review_items_label
        if unit.has_annotated_copy:
            back_action = action(OPEN_ANNOTATED_COPY, chapter_id=unit.id, unit_id=unit.id)
            back_action.label = copy.back_to_annotated_label
            actions.append(back_action)
        else:
            back_action = action(READ_ORIGINAL, chapter_id=unit.id, unit_id=unit.id)
            back_action.label = copy.back_to_source_label
            actions.append(back_action)

        title = copy.complete_title if unit.next_unit_id else copy.final_complete_title
        return [
            AgentCard(
                id=f"unit-{unit.id}-complete",
                type="progress",
                title=title,
                body=self._vocab_body(unit, copy.complete_prefix, copy=copy),
                actions=actions,
            )
        ]

    def chapter_cards(self, unit: ReadingUnitState) -> list[AgentCard]:
        return self.unit_cards(unit)

    def unit_cards(self, unit: ReadingUnitState) -> list[AgentCard]:
        """Select the card variant from the user's progress on one unit."""
        return self.start_unit(unit)

    def _unit_title(self, unit: ReadingUnitState, prefix: str, *, copy: CardCopy) -> str:
        return copy.unit_body_template.format(
            prefix=prefix,
            book_title=unit.book_title,
            chapter_no=unit.chapter_no,
            chapter_title=unit.chapter_title,
            unit_id=unit.id,
        )

    def _vocab_body(self, unit: ReadingUnitState, prefix: str, *, copy: CardCopy) -> str:
        if unit.vocab_count <= 0:
            return prefix
        word_label = copy.learning_item_singular if unit.vocab_count == 1 else copy.learning_item_plural
        return copy.review_body_template.format(
            prefix=prefix,
            count=unit.vocab_count,
            scope=copy.learning_item_scope,
            item_label=word_label,
        )

    def _copy_for(self, unit: ReadingUnitState) -> CardCopy:
        return self._copy_for_profile(unit.profile_id)

    def _copy_for_profile(self, profile_id: str | None = None) -> CardCopy:
        if self.profile_registry is None:
            return self.copy
        return self.profile_registry.get(profile_id).card_copy
