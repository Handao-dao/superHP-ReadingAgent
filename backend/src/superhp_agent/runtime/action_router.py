"""Deterministic router for guided reading cards.

This is not an LLM router. It only inspects current reading state and chooses
which predefined card templates should be shown.
"""

from __future__ import annotations

from superhp_agent.runtime.cards import ReadingCardBuilder
from superhp_agent.runtime.reading_state import ReadingStateReader, ReadingUnitState
from superhp_agent.schemas import AgentCard


class ReadingFlowRouter:
    def __init__(
        self,
        state_reader: ReadingStateReader,
        card_builder: ReadingCardBuilder | None = None,
    ):
        self.state_reader = state_reader
        self.card_builder = card_builder or ReadingCardBuilder()

    def inspect(self, current_chapter_id: str | None = None, current_unit_id: str | None = None) -> list[AgentCard]:
        unit_id = current_unit_id or current_chapter_id
        if unit_id:
            current = self.state_reader.get_state(unit_id)
            if current is not None:
                return self.card_builder.unit_cards(current)

        current = self.state_reader.current_state()
        if current is not None:
            return self.card_builder.unit_cards(current)

        first = self.state_reader.first_state()
        if first is None:
            return self.card_builder.empty_corpus()
        return self.card_builder.start_reading(first)

    def cards_for_unit(self, unit: ReadingUnitState) -> list[AgentCard]:
        return self.card_builder.unit_cards(unit)

    def cards_for_chapter(self, chapter: ReadingUnitState) -> list[AgentCard]:
        return self.cards_for_unit(chapter)