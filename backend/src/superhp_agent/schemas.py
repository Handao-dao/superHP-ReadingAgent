"""HTTP request and response schemas owned by the API adapter."""

from typing import Literal

from pydantic import BaseModel, Field

from superhp_agent.contracts import (
    BookEntryKind,
    ReadingPreference,
    RecommendationAgentPhase,
    RecommendationOrigin,
)


class ProfileMeta(BaseModel):
    id: str
    language_id: str
    label: str
    renderer_hint: str = "english_novel"
    is_default: bool = False


class LibraryBookMeta(BaseModel):
    id: str
    order: int


class LibraryCollectionMeta(BaseModel):
    id: str
    profile_id: str
    title: str
    author: str = ""
    order: int
    books: list[LibraryBookMeta]


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


class CreateRecommendationSessionRequest(BaseModel):
    """Known preferences available before the first recommendation turn."""

    origin: RecommendationOrigin = RecommendationOrigin.ONBOARDING
    preferred_genres: list[str] = Field(default_factory=list, max_length=10)
    excluded_traits: list[str] = Field(default_factory=list, max_length=10)
    reading_preference: ReadingPreference = ReadingPreference.BALANCED
    user_notes: str = Field(default="", max_length=2000)


class ContinueRecommendationSessionRequest(BaseModel):
    """One visible user message sent to a paused recommendation session."""

    message: str = Field(min_length=1, max_length=4000)


class RecommendationChatMessage(BaseModel):
    """A user-visible message; internal Tool messages are never exposed."""

    role: Literal["user", "assistant"]
    content: str


class RecommendationBookCard(BaseModel):
    """Verified local-catalog metadata rendered by the chat page."""

    catalog_id: str
    title_en: str
    title_zh: str = ""
    author: str = ""
    entry_kind: BookEntryKind = BookEntryKind.UNKNOWN
    lexile_min: int
    lexile_max: int
    genres: list[str] = Field(default_factory=list)


class RecommendationSessionResponse(BaseModel):
    """Restorable public view of one recommendation conversation."""

    session_id: str
    phase: RecommendationAgentPhase
    messages: list[RecommendationChatMessage]
    recommended_books: list[RecommendationBookCard] = Field(default_factory=list)
    error_code: str = ""
