"""Shared API schemas."""

from pydantic import BaseModel, Field


class ReadingUnitMeta(BaseModel):
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

    @property
    def summary_zh(self) -> str:
        return self.summary


class ReadingUnitDetail(BaseModel):
    meta: ReadingUnitMeta
    body: str
    body_kind: str = Field(description="source or annotated")


ChapterMeta = ReadingUnitMeta
ChapterDetail = ReadingUnitDetail


class VocabularyEntry(BaseModel):
    id: int
    word: str
    translation: str
    global_translation: str
    mastered: bool = False
    context: str = ""
    encounter_count: int = 1
    unit_id: str
    chapter_id: str
    first_seen_at: str = ""
    last_seen_at: str = ""


class AgentAction(BaseModel):
    id: str
    label: str
    payload: dict = Field(default_factory=dict)


class AgentCard(BaseModel):
    id: str
    type: str
    title: str
    body: str
    actions: list[AgentAction] = Field(default_factory=list)