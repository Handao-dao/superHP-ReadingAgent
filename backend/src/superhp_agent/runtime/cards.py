"""Deterministic guided-card templates for the reading flow."""

from __future__ import annotations

from superhp_agent.runtime.actions import (
    GENERATE_ANNOTATION,
    MARK_CHAPTER_READ,
    OPEN_ANNOTATED_COPY,
    OPEN_CHAPTER,
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
    def empty_corpus(self) -> list[AgentCard]:
        return [
            AgentCard(
                id="empty-corpus",
                type="setup",
                title="还没有可阅读的文本",
                body="请先把章节 Markdown 放入 corpus/ 目录。",
                actions=[],
            )
        ]

    def start_reading(self, unit: ReadingUnitState) -> list[AgentCard]:
        return [
            AgentCard(
                id="start-reading",
                type="reading",
                title="开始阅读？",
                body=self._unit_title(unit, "可以从"),
                actions=[action(OPEN_CHAPTER, chapter_id=unit.id, unit_id=unit.id)],
            )
        ]

    def chapter_cards(self, unit: ReadingUnitState) -> list[AgentCard]:
        return self.unit_cards(unit)

    def unit_cards(self, unit: ReadingUnitState) -> list[AgentCard]:
        """Select the card variant from the user's progress on one unit."""
        if unit.is_read:
            return self._read_unit(unit)
        if not unit.has_annotated_copy:
            return self._unannotated_unit(unit)
        return self._annotated_unread_unit(unit)

    def _unannotated_unit(self, unit: ReadingUnitState) -> list[AgentCard]:
        body = f"第 {unit.chapter_no} 章第 {unit.section_no}/{unit.section_count} 节还没有译注副本。"
        if unit.summary:
            body += f" 本章概要：{unit.summary}"
        return [
            AgentCard(
                id=f"unit-{unit.id}-unannotated",
                type="annotation",
                title="要生成这一节的译注吗？",
                body=body,
                actions=[
                    action(GENERATE_ANNOTATION, chapter_id=unit.id, unit_id=unit.id),
                    action(READ_ORIGINAL, chapter_id=unit.id, unit_id=unit.id),
                ],
            )
        ]

    def _annotated_unread_unit(self, unit: ReadingUnitState) -> list[AgentCard]:
        actions = [
            action(OPEN_ANNOTATED_COPY, chapter_id=unit.id, unit_id=unit.id),
            action(MARK_CHAPTER_READ, chapter_id=unit.id, unit_id=unit.id),
        ]
        if unit.vocab_count > 0:
            actions.insert(1, action(REVIEW_CHAPTER_VOCAB, chapter_id=unit.id, unit_id=unit.id))
        return [
            AgentCard(
                id=f"unit-{unit.id}-continue",
                type="reading",
                title="继续阅读这一节吗？",
                body=self._vocab_body(unit, "这一节已经有译注副本，可以继续阅读。"),
                actions=actions,
            )
        ]

    def _read_unit(self, unit: ReadingUnitState) -> list[AgentCard]:
        # Review comes before navigation so the user can consolidate vocabulary
        # while the just-finished unit is still fresh.
        actions = []
        if unit.vocab_count > 0:
            actions.append(action(REVIEW_CHAPTER_VOCAB, chapter_id=unit.id, unit_id=unit.id))
        if unit.next_unit_id:
            actions.append(action(START_NEXT_CHAPTER, chapter_id=unit.next_unit_id, unit_id=unit.next_unit_id))
        actions.append(action(OPEN_ANNOTATED_COPY, chapter_id=unit.id, unit_id=unit.id))
        return [
            AgentCard(
                id=f"unit-{unit.id}-read",
                type="progress",
                title="准备进入下一步吗？",
                body=self._vocab_body(unit, "这一节已经标记为已读。"),
                actions=actions,
            )
        ]

    @staticmethod
    def _unit_title(unit: ReadingUnitState, prefix: str) -> str:
        return (
            f"{prefix}《{unit.book_title}》第 {unit.chapter_no} 章 "
            f"{unit.chapter_title} 的第 {unit.section_no}/{unit.section_count} 节开始。"
        )

    @staticmethod
    def _vocab_body(unit: ReadingUnitState, prefix: str) -> str:
        if unit.vocab_count <= 0:
            return prefix
        return f"{prefix} 本节目前关联了 {unit.vocab_count} 个生词。"