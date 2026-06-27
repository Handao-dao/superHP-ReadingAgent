"""Deterministic router for guided reading cards.

This is not an LLM router. It only inspects current reading state and chooses
which predefined card templates should be shown.
"""

from __future__ import annotations

from superhp_agent.runtime.cards import ReadingCardBuilder
from superhp_agent.runtime.reading_state import ReadingStateReader, ReadingUnitState
from superhp_agent.schemas import AgentCard

CARD_PHASE_START = "start"
CARD_PHASE_COMPLETE = "complete"


class ReadingFlowRouter:
    """Choose the next guided cards from read-only state.

    The router is deliberately deterministic in v1. It does not execute actions
    or call an LLM; it simply decides which card templates best match the user's
    current unit.
    """
    def __init__(
        self,
        state_reader: ReadingStateReader,
        card_builder: ReadingCardBuilder | None = None,
    ):
        self.state_reader = state_reader
        self.card_builder = card_builder or ReadingCardBuilder()

    def inspect(
        self,
        current_chapter_id: str | None = None,
        current_unit_id: str | None = None,
        phase: str = CARD_PHASE_START,
        profile_id: str | None = None,
    ) -> list[AgentCard]:
        """Return the cards the frontend should offer next."""
        unit_id = current_unit_id or current_chapter_id
        if unit_id:
            current = self.state_reader.get_state(unit_id, profile_id=profile_id)
            if current is not None:
                return self._cards_for_phase(current, phase)

        current = self.state_reader.current_state(profile_id=profile_id)
        if current is not None:
            return self._cards_for_phase(current, phase)

        first = self.state_reader.first_state(profile_id=profile_id)
        if first is None:
            return self.card_builder.empty_corpus(profile_id=profile_id)
        return self.card_builder.start_reading(first)

    def resolve_unit_id(
        self,
        current_chapter_id: str | None = None,
        current_unit_id: str | None = None,
        profile_id: str | None = None,
    ) -> str | None:
        """Return the unit id that inspect would use for cards."""
        unit_id = current_unit_id or current_chapter_id
        if unit_id and self.state_reader.get_state(unit_id, profile_id=profile_id) is not None:
            return unit_id
        current = self.state_reader.current_state(profile_id=profile_id)
        if current is not None:
            return current.id
        first = self.state_reader.first_state(profile_id=profile_id)
        return first.id if first is not None else None

    def cards_for_unit(self, unit: ReadingUnitState) -> list[AgentCard]:
        return self.card_builder.unit_cards(unit)

    def cards_for_chapter(self, chapter: ReadingUnitState) -> list[AgentCard]:
        return self.cards_for_unit(chapter)

    def _cards_for_phase(self, unit: ReadingUnitState, phase: str) -> list[AgentCard]:
        if phase == CARD_PHASE_COMPLETE:
            return self.card_builder.complete_unit(unit)
        return self.card_builder.start_unit(unit)
