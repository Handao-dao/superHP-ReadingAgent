"""Guided reading action identifiers and constructors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from superhp_agent.contracts import AgentAction

OPEN_CHAPTER: Final = "open_chapter"
GENERATE_ANNOTATION: Final = "generate_annotation"
OPEN_ANNOTATED_COPY: Final = "open_annotated_copy"
MARK_CHAPTER_READ: Final = "mark_chapter_read"
REVIEW_CHAPTER_VOCAB: Final = "review_chapter_vocab"
START_NEXT_CHAPTER: Final = "start_next_chapter"
READ_ORIGINAL: Final = "read_original"


@dataclass(frozen=True)
class ActionTemplate:
    id: str
    label: str

    def build(self, **payload: object) -> AgentAction:
        return AgentAction(id=self.id, label=self.label, payload=dict(payload))


ACTIONS: Final[dict[str, ActionTemplate]] = {
    OPEN_CHAPTER: ActionTemplate(OPEN_CHAPTER, "Open"),
    GENERATE_ANNOTATION: ActionTemplate(GENERATE_ANNOTATION, "Generate"),
    OPEN_ANNOTATED_COPY: ActionTemplate(OPEN_ANNOTATED_COPY, "Annotated"),
    MARK_CHAPTER_READ: ActionTemplate(MARK_CHAPTER_READ, "Mark Read"),
    REVIEW_CHAPTER_VOCAB: ActionTemplate(REVIEW_CHAPTER_VOCAB, "Vocab"),
    START_NEXT_CHAPTER: ActionTemplate(START_NEXT_CHAPTER, "Next"),
    READ_ORIGINAL: ActionTemplate(READ_ORIGINAL, "Original"),
}


def action(action_id: str, **payload: object) -> AgentAction:
    template = ACTIONS[action_id]
    return template.build(**payload)
