"""Read-only reading contracts shared across application boundaries.

These models describe reading-unit content and guided cards returned to a
client. They do not load corpus files, calculate reading state, choose cards,
execute actions, or define HTTP/WebSocket envelopes.
"""

from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from superhp_agent.contracts.actions import AgentAction


@dataclass(frozen=True)
class ReadingProgressSnapshot:
    """Single-user reading pointer and per-unit opened/read state."""

    current_unit_id: str = ""
    opened_unit_ids: list[str] = field(default_factory=list)
    read_unit_ids: list[str] = field(default_factory=list)


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

    @property
    def summary_zh(self) -> str:
        return self.summary


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
