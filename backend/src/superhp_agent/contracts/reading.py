"""Read-only reading contracts shared across application boundaries.

These models describe reading-unit content and guided cards returned to a
client. They do not load corpus files, calculate reading state, choose cards,
execute actions, or define HTTP/WebSocket envelopes.
"""

from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from superhp_agent.contracts.actions import AgentAction
from superhp_agent.domain.reading_support import validate_annotation_target


@dataclass(frozen=True)
class ReadingProgressSnapshot:
    """Single-user reading pointer and per-unit opened/read state."""

    current_unit_id: str = ""
    opened_unit_ids: list[str] = field(default_factory=list)
    read_unit_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ChapterReadingCheckpoint:
    """Frozen reading facts captured when one complete chapter first finishes."""

    book_id: str
    chapter_id: str
    chapter_no: int
    unit_ids: tuple[str, ...]
    word_count: int
    lookup_count: int
    annotated_lookup_count: int
    annotation_target: int | None = None
    completed_at: str = ""

    def __post_init__(self) -> None:
        if not self.book_id.strip():
            raise ValueError("book_id is required")
        if not self.chapter_id.strip():
            raise ValueError("chapter_id is required")
        if self.chapter_no < 1:
            raise ValueError("chapter_no must be positive")
        if not self.unit_ids or any(not unit_id.strip() for unit_id in self.unit_ids):
            raise ValueError("unit_ids must contain non-empty values")
        if self.word_count < 0:
            raise ValueError("word_count must not be negative")
        if not 0 <= self.annotated_lookup_count <= self.lookup_count:
            raise ValueError(
                "annotated_lookup_count must be between 0 and lookup_count"
            )
        if self.annotation_target is not None:
            validate_annotation_target(self.annotation_target)


class ReadingUnitMeta(BaseModel):
    """Stable metadata exposed for one readable unit."""

    id: str
    chapter_id: str
    book_id: str
    book_title: str
    chapter_no: int
    chapter_title: str
    section_no: int = 1
    section_count: int = 1
    summary: str = ""
    has_annotated_copy: bool = False
    status: str = "unread"
    vocab_count: int = 0
    profile_id: str = "english_novel"
    language_id: str = "en"

class ReadingUnitDetail(BaseModel):
    """One reading unit together with source or annotated body text."""

    meta: ReadingUnitMeta
    body: str
    body_kind: str = Field(description="source or annotated")


class AgentCard(BaseModel):
    """One deterministic guided-reading choice card."""

    id: str
    type: str
    title: str
    body: str
    actions: list[AgentAction] = Field(default_factory=list)
