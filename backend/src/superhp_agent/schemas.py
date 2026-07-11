"""Shared API schemas and compatibility exports.

New cross-layer contracts live under ``superhp_agent.contracts``. This module
keeps their historical import paths available while the remaining API models
are migrated incrementally.
"""

from pydantic import BaseModel

from superhp_agent.contracts import (
    AgentAction as AgentAction,
)
from superhp_agent.contracts import (
    AgentCard as AgentCard,
)
from superhp_agent.contracts import (
    ReadingUnitDetail as ReadingUnitDetail,
)
from superhp_agent.contracts import (
    ReadingUnitMeta as ReadingUnitMeta,
)

ChapterMeta = ReadingUnitMeta
ChapterDetail = ReadingUnitDetail


class ProfileMeta(BaseModel):
    id: str
    language_id: str
    label: str
    renderer_hint: str = "english_novel"
    is_default: bool = False


class VocabularyEntry(BaseModel):
    id: int
    book_id: str
    profile_id: str
    language_id: str
    word: str
    translation: str
    global_translation: str
    pos: str = "other"
    mastered: bool = False
    context: str = ""
    encounter_count: int = 1
    unit_id: str
    chapter_id: str
    first_seen_at: str = ""
    last_seen_at: str = ""


class WordLookupRequest(BaseModel):
    word: str
    sentence: str = ""
    profile_id: str | None = None


class WordLookupResult(BaseModel):
    word: str
    word_cn: str
    pos: str = "other"
    sentence_cn: str = ""


class AddVocabularyRequest(BaseModel):
    word: str
    translation: str
    context: str = ""
    pos: str = "other"
    unit_id: str


class AddVocabularyResponse(BaseModel):
    id: int
    book_id: str
    profile_id: str
    language_id: str
    word: str
    translation: str
    pos: str = "other"
    unit_id: str


class SetMasteredRequest(BaseModel):
    mastered: bool


class MarkByWordRequest(BaseModel):
    word: str
    mastered: bool
    profile_id: str | None = None


class BookmarkEntry(BaseModel):
    id: int
    unit_id: str
    chapter_id: str
    body_kind: str
    page_index: int
    progress_ratio: float = 0
    total_pages: int = 0
    label: str = ""
    excerpt: str = ""
    paragraph_index: int = -1
    created_at: str = ""


class AddBookmarkRequest(BaseModel):
    unit_id: str
    body_kind: str
    page_index: int = 0
    progress_ratio: float = 0
    total_pages: int = 0
    label: str = ""
    excerpt: str = ""
    paragraph_index: int = -1


class MutationResponse(BaseModel):
    ok: bool = True
