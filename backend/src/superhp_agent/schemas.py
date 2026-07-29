"""HTTP request and response schemas owned by the API adapter."""

from typing import Literal

from pydantic import BaseModel, Field

from superhp_agent.contracts import (
    BookEntryKind,
    ConversationMemoryKind,
    ConversationMemoryStatus,
    ReadingCompanionEpisodeEndReason,
    ReadingCompanionEpisodeTrigger,
    ReadingCompanionSessionStatus,
    ReadingDifficultyState,
    ReadingPreference,
    RecommendationAgentPhase,
    RecommendationOrigin,
)
from superhp_agent.domain.reading_difficulty_prompt import (
    ReadingDifficultyPromptStatus,
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
    unit_id: str | None = None
    was_annotated: bool = False


class WordLookupResult(BaseModel):
    word: str
    word_cn: str
    pos: str = "other"
    sentence_cn: str = ""


class ReadingDifficultyEvidenceResponse(BaseModel):
    """Measured fields currently available from completed reading units."""

    observed_word_count: int
    observed_chapter_count: int
    lookup_density: float
    unique_lookup_density: float
    repeated_lookup_density: float
    annotated_lookup_density: float


class ReadingDifficultyObservationResponse(BaseModel):
    """Read-only monitoring state; it does not imply a user-facing alert."""

    book_id: str
    state: ReadingDifficultyState
    window_ready: bool
    observed_unit_ids: list[str] = Field(default_factory=list)
    evidence: ReadingDifficultyEvidenceResponse


class ReadingDifficultyPromptEvidenceResponse(
    ReadingDifficultyEvidenceResponse
):
    """Complete evidence snapshot retained with a user-facing prompt."""

    actual_annotation_density: float = 0
    annotation_target: int | None = None


class ReadingDifficultyPromptResponse(BaseModel):
    """Persisted prompt lifecycle exposed for recovery and diagnostics."""

    book_id: str
    chapter_id: str
    status: ReadingDifficultyPromptStatus
    cooldown_chapters_remaining: int
    recommendation_session_id: str = ""
    evidence: ReadingDifficultyPromptEvidenceResponse


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


class CreateDifficultyHandoffRequest(BaseModel):
    """User-authorized transition identified by a trusted local book id."""

    session_id: str = Field(default="", max_length=200)
    book_id: str = Field(min_length=1, max_length=200)
    preserve_genre_by_default: bool = True


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
    origin: RecommendationOrigin
    phase: RecommendationAgentPhase
    messages: list[RecommendationChatMessage]
    recommended_books: list[RecommendationBookCard] = Field(default_factory=list)
    selected_catalog_id: str = ""
    error_code: str = ""


class CreateReadingCompanionSessionRequest(BaseModel):
    """Open one manual reading Episode at a trusted local reading unit."""

    session_id: str = Field(default="", max_length=200)
    current_unit_id: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=4000)
    selected_text: str = Field(default="", max_length=12000)


class ContinueReadingCompanionSessionRequest(BaseModel):
    """One visible user message appended to an active manual Episode."""

    message: str = Field(min_length=1, max_length=4000)


class EndReadingCompanionEpisodeRequest(BaseModel):
    """Explicitly close the current Episode and request passive summary."""

    reason: ReadingCompanionEpisodeEndReason = (
        ReadingCompanionEpisodeEndReason.USER_ENDED
    )


class ReadingCompanionChatMessage(BaseModel):
    """A public transcript item; tool traffic remains backend-internal."""

    role: Literal["user", "assistant"]
    content: str


class ReadingCompanionSessionResponse(BaseModel):
    """Restorable public view of one durable reading conversation."""

    session_id: str
    episode_id: str
    trigger: ReadingCompanionEpisodeTrigger
    book_id: str
    chapter_id: str
    unit_id: str
    selected_text: str = ""
    messages: list[ReadingCompanionChatMessage]
    error_code: str = ""


class ReadingCompanionSessionEnvelope(BaseModel):
    """Long-lived Session plus its optional active Episode projection."""

    session_id: str
    status: ReadingCompanionSessionStatus
    active_episode: ReadingCompanionSessionResponse | None = None


class ReadingCompanionMemoryResponse(BaseModel):
    """Public result of one passive Episode-summary attempt."""

    session_id: str
    episode_id: str
    kind: ConversationMemoryKind
    revision: int
    status: ConversationMemoryStatus
    summary: str = ""
    error_code: str = ""
