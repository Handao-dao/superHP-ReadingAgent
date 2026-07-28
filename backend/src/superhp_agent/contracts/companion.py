"""Stable boundaries for the future long-lived reading companion.

These immutable contracts describe session and episode lifecycles, compressed
conversation memory, and spoiler-safe retrieval from completed chapters. They
do not persist messages, generate summaries, search corpus files, or call a
model.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from superhp_agent.contracts.llm import LLMToolCall


class ReadingCompanionSessionStatus(StrEnum):
    """Long-lived availability of one reader's companion conversation."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class ReadingCompanionEpisodeTrigger(StrEnum):
    """Explicit product event that opened one bounded conversation episode."""

    ONBOARDING = "onboarding"
    MANUAL_READING = "manual_reading"
    DIFFICULTY_ALERT = "difficulty_alert"
    USER_REQUEST = "user_request"


class ReadingCompanionEpisodeState(StrEnum):
    """Lifecycle of one invocation episode inside a long-lived session."""

    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class ReadingCompanionEpisodeEndReason(StrEnum):
    """Stable reason why an episode stopped accepting new turns."""

    BOOK_SELECTED = "book_selected"
    CONTINUE_READING = "continue_reading"
    USER_ENDED = "user_ended"
    USER_ABANDONED = "user_abandoned"
    BOOK_CHANGED = "book_changed"
    UNRECOVERABLE_ERROR = "unrecoverable_error"


class ReadingCompanionMessageRole(StrEnum):
    """Native transcript roles retained across companion model turns."""

    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ConversationMemoryKind(StrEnum):
    """Whether a summary closes an episode or compacts an active one."""

    EPISODE_SUMMARY = "episode_summary"
    ROLLING_COMPACTION = "rolling_compaction"


class ConversationMemoryStatus(StrEnum):
    """Generation state of one append-only memory revision."""

    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


@dataclass(frozen=True)
class ReadingCompanionSession:
    """Long-lived conversation identity for the current reader.

    ``reader_key`` is deliberately separate from text ``profile_id``. The
    single-user prototype may use ``default`` until real user identity exists.
    """

    session_id: str
    reader_key: str = "default"
    status: ReadingCompanionSessionStatus = ReadingCompanionSessionStatus.ACTIVE
    active_episode_id: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not self.session_id.strip():
            raise ValueError("session_id must not be empty")
        if not self.reader_key.strip():
            raise ValueError("reader_key must not be empty")
        if (
            self.status is ReadingCompanionSessionStatus.ARCHIVED
            and self.active_episode_id
        ):
            raise ValueError("archived session must not have an active episode")


@dataclass(frozen=True)
class ReadingCompanionEpisode:
    """One explicitly triggered conversation range within a session."""

    episode_id: str
    session_id: str
    trigger: ReadingCompanionEpisodeTrigger
    start_message_id: str
    state: ReadingCompanionEpisodeState = ReadingCompanionEpisodeState.ACTIVE
    book_id: str = ""
    chapter_id: str = ""
    unit_id: str = ""
    selected_text: str = ""
    end_message_id: str = ""
    end_reason: ReadingCompanionEpisodeEndReason | None = None
    created_at: str = ""
    ended_at: str = ""

    def __post_init__(self) -> None:
        if not self.episode_id.strip():
            raise ValueError("episode_id must not be empty")
        if not self.session_id.strip():
            raise ValueError("session_id must not be empty")
        if not self.start_message_id.strip():
            raise ValueError("start_message_id must not be empty")
        if self.chapter_id and not self.book_id:
            raise ValueError("chapter_id requires book_id")
        if self.unit_id and not self.chapter_id:
            raise ValueError("unit_id requires chapter_id")
        if self.selected_text and not self.chapter_id:
            raise ValueError("selected_text requires chapter_id")
        if self.trigger is ReadingCompanionEpisodeTrigger.MANUAL_READING:
            if not self.book_id or not self.chapter_id or not self.unit_id:
                raise ValueError(
                    "manual_reading episode requires book, chapter, and unit"
                )
        if self.trigger is ReadingCompanionEpisodeTrigger.DIFFICULTY_ALERT:
            if not self.book_id:
                raise ValueError("difficulty_alert episode requires book_id")

        is_active = self.state is ReadingCompanionEpisodeState.ACTIVE
        if is_active and (
            self.end_message_id or self.end_reason is not None or self.ended_at
        ):
            raise ValueError("active episode must not contain end metadata")
        if not is_active:
            if not self.end_message_id.strip():
                raise ValueError("ended episode requires end_message_id")
            if self.end_reason is None:
                raise ValueError("ended episode requires end_reason")


@dataclass(frozen=True)
class ReadingCompanionMessage:
    """One persistent-ready user, assistant, or tool transcript message."""

    message_id: str
    session_id: str
    episode_id: str
    role: ReadingCompanionMessageRole
    content: str = ""
    tool_calls: tuple[LLMToolCall, ...] = ()
    tool_call_id: str = ""
    tool_name: str = ""
    is_error: bool = False

    def __post_init__(self) -> None:
        for field_name, value in (
            ("message_id", self.message_id),
            ("session_id", self.session_id),
            ("episode_id", self.episode_id),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        if self.role is ReadingCompanionMessageRole.USER:
            if not self.content.strip():
                raise ValueError("user companion message must not be empty")
            if self.tool_calls or self.tool_call_id or self.tool_name:
                raise ValueError("user companion message contains tool data")
            return
        if self.role is ReadingCompanionMessageRole.ASSISTANT:
            if not self.content.strip() and not self.tool_calls:
                raise ValueError(
                    "assistant companion message requires content or tool calls"
                )
            if self.tool_call_id or self.tool_name:
                raise ValueError(
                    "assistant companion message contains tool-result data"
                )
            return
        if not self.content.strip():
            raise ValueError("companion tool result must not be empty")
        if not self.tool_call_id.strip() or not self.tool_name.strip():
            raise ValueError(
                "companion tool result requires call id and tool name"
            )
        if self.tool_calls:
            raise ValueError(
                "companion tool result contains assistant tool calls"
            )


@dataclass(frozen=True)
class ReadingCompanionRunState:
    """In-memory active Episode state passed between companion Loop calls."""

    episode: ReadingCompanionEpisode
    conversation: tuple[ReadingCompanionMessage, ...]
    tool_call_count: int = 0
    error_code: str = ""
    context_start_index: int = 0

    def __post_init__(self) -> None:
        if self.episode.state is not ReadingCompanionEpisodeState.ACTIVE:
            raise ValueError("companion run requires an active episode")
        if not self.conversation:
            raise ValueError("companion run requires a conversation")
        if self.conversation[0].message_id != self.episode.start_message_id:
            raise ValueError(
                "first companion message must match episode start_message_id"
            )
        if self.conversation[0].role is not ReadingCompanionMessageRole.USER:
            raise ValueError("companion conversation must start with a user")
        if any(
            message.session_id != self.episode.session_id
            or message.episode_id != self.episode.episode_id
            for message in self.conversation
        ):
            raise ValueError(
                "companion messages must belong to the active episode"
            )
        message_ids = [
            message.message_id for message in self.conversation
        ]
        if len(set(message_ids)) != len(message_ids):
            raise ValueError("companion message ids must be unique")
        if self.tool_call_count < 0:
            raise ValueError("tool_call_count must not be negative")
        if not 0 <= self.context_start_index < len(self.conversation):
            raise ValueError("invalid companion context_start_index")
        if (
            self.conversation[self.context_start_index].role
            is not ReadingCompanionMessageRole.USER
        ):
            raise ValueError("companion context must start with a user message")


@dataclass(frozen=True)
class ReadingCompanionObservation:
    """Trusted facts and transcript supplied to one companion model turn."""

    state: ReadingCompanionRunState
    book_title: str
    chapter_title: str
    chapter_no: int
    remaining_tool_calls: int
    conversation_memory: str = ""

    def __post_init__(self) -> None:
        if not self.book_title.strip() or not self.chapter_title.strip():
            raise ValueError("companion observation requires reading titles")
        if self.chapter_no < 1:
            raise ValueError("chapter_no must be positive")
        if self.remaining_tool_calls < 0:
            raise ValueError("remaining_tool_calls must not be negative")


@dataclass(frozen=True)
class ReadingCompanionReply:
    """User-facing response plus resumable active Episode state."""

    state: ReadingCompanionRunState
    message: str
    error_code: str = ""

    def __post_init__(self) -> None:
        if not self.message.strip():
            raise ValueError("companion reply message must not be empty")


@dataclass(frozen=True)
class ConversationMemory:
    """One append-only summary revision covering an exact message range."""

    memory_id: str
    session_id: str
    episode_id: str
    kind: ConversationMemoryKind
    revision: int
    source_start_message_id: str
    source_end_message_id: str
    status: ConversationMemoryStatus = ConversationMemoryStatus.PENDING
    summary: str = ""
    error_code: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    created_at: str = ""

    def __post_init__(self) -> None:
        for field_name, value in (
            ("memory_id", self.memory_id),
            ("session_id", self.session_id),
            ("episode_id", self.episode_id),
            ("source_start_message_id", self.source_start_message_id),
            ("source_end_message_id", self.source_end_message_id),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        if self.revision < 1:
            raise ValueError("revision must be positive")
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise ValueError("memory token usage must not be negative")
        if self.status is ConversationMemoryStatus.READY:
            if not self.summary.strip():
                raise ValueError("ready memory requires summary")
            if self.error_code:
                raise ValueError("ready memory must not contain error_code")
        elif self.status is ConversationMemoryStatus.PENDING:
            if self.summary or self.error_code:
                raise ValueError(
                    "pending memory must not contain summary or error_code"
                )
        else:
            if self.summary:
                raise ValueError("failed memory must not contain summary")
            if not self.error_code.strip():
                raise ValueError("failed memory requires error_code")


@dataclass(frozen=True)
class CompletedChapterScope:
    """One fully completed chapter made searchable by a trusted checkpoint."""

    chapter_id: str
    chapter_no: int
    unit_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.chapter_id.strip():
            raise ValueError("chapter_id must not be empty")
        if self.chapter_no < 1:
            raise ValueError("chapter_no must be positive")
        if not self.unit_ids or any(
            not unit_id.strip() for unit_id in self.unit_ids
        ):
            raise ValueError("unit_ids must contain non-empty values")
        if len(set(self.unit_ids)) != len(self.unit_ids):
            raise ValueError("unit_ids must be unique")


@dataclass(frozen=True)
class PreviousReadingScope:
    """Trusted prior-chapter boundary shared by reading-history tools."""

    book_id: str
    current_chapter_id: str
    current_chapter_no: int
    completed_chapters: tuple[CompletedChapterScope, ...] = ()

    def __post_init__(self) -> None:
        if not self.book_id.strip():
            raise ValueError("book_id must not be empty")
        if not self.current_chapter_id.strip():
            raise ValueError("current_chapter_id must not be empty")
        if self.current_chapter_no < 1:
            raise ValueError("current_chapter_no must be positive")

        chapter_ids = [
            chapter.chapter_id for chapter in self.completed_chapters
        ]
        if len(set(chapter_ids)) != len(chapter_ids):
            raise ValueError("completed chapter ids must be unique")
        chapter_numbers = [
            chapter.chapter_no for chapter in self.completed_chapters
        ]
        if chapter_numbers != sorted(chapter_numbers):
            raise ValueError("completed chapters must be chronological")
        if len(set(chapter_numbers)) != len(chapter_numbers):
            raise ValueError("completed chapter numbers must be unique")
        if self.current_chapter_id in chapter_ids:
            raise ValueError(
                "current chapter must not be inside completed chapters"
            )
        if any(
            chapter.chapter_no >= self.current_chapter_no
            for chapter in self.completed_chapters
        ):
            raise ValueError(
                "completed chapters must precede the current chapter"
            )
        unit_ids = [
            unit_id
            for chapter in self.completed_chapters
            for unit_id in chapter.unit_ids
        ]
        if len(set(unit_ids)) != len(unit_ids):
            raise ValueError(
                "completed chapter unit ids must be globally unique"
            )

    @property
    def searchable_unit_ids(self) -> tuple[str, ...]:
        """Return stable unit ids allowed to both history tools."""
        return tuple(
            unit_id
            for chapter in self.completed_chapters
            for unit_id in chapter.unit_ids
        )


@dataclass(frozen=True)
class AgentToolExecutionContext:
    """Trusted per-run state passed beside, never inside, model arguments."""

    session_id: str
    episode_id: str
    language_id: str = ""
    previous_reading_scope: PreviousReadingScope | None = None

    def __post_init__(self) -> None:
        if not self.session_id.strip():
            raise ValueError("session_id must not be empty")
        if not self.episode_id.strip():
            raise ValueError("episode_id must not be empty")
        if self.previous_reading_scope is not None and not self.language_id.strip():
            raise ValueError(
                "reading tool context requires language_id"
            )


@dataclass(frozen=True)
class PreviousChapterSearchRequest:
    """Internal request for keyword evidence from completed prior chapters."""

    query: str
    scope: PreviousReadingScope
    max_chapters: int = 4

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise ValueError("query must not be empty")
        if not 1 <= self.max_chapters <= 10:
            raise ValueError("max_chapters must be between 1 and 10")


@dataclass(frozen=True)
class PreviousChapterExcerpt:
    """One bounded source paragraph supporting a prior-chapter match."""

    unit_id: str
    text: str

    def __post_init__(self) -> None:
        if not self.unit_id.strip():
            raise ValueError("excerpt unit_id must not be empty")
        if not self.text.strip():
            raise ValueError("excerpt text must not be empty")


@dataclass(frozen=True)
class PreviousChapterMatch:
    """Summary and source evidence grouped under one completed chapter."""

    chapter_id: str
    chapter_no: int
    chapter_title: str
    summary: str = ""
    excerpts: tuple[PreviousChapterExcerpt, ...] = ()

    def __post_init__(self) -> None:
        if not self.chapter_id.strip():
            raise ValueError("match chapter_id must not be empty")
        if self.chapter_no < 1:
            raise ValueError("match chapter_no must be positive")
        if not self.chapter_title.strip():
            raise ValueError("match chapter_title must not be empty")
        if not self.summary.strip() and not self.excerpts:
            raise ValueError("chapter match requires summary or excerpts")


@dataclass(frozen=True)
class PreviousChapterSearchResult:
    """Chronological, spoiler-safe evidence returned for prior chapters."""

    request: PreviousChapterSearchRequest
    matches: tuple[PreviousChapterMatch, ...] = ()
    truncated: bool = False

    def __post_init__(self) -> None:
        if len(self.matches) > self.request.max_chapters:
            raise ValueError("too many previous chapter matches")
        chapter_numbers = [match.chapter_no for match in self.matches]
        if chapter_numbers != sorted(chapter_numbers):
            raise ValueError(
                "previous chapter matches must be chronological"
            )
        chapter_ids = [match.chapter_id for match in self.matches]
        if len(set(chapter_ids)) != len(chapter_ids):
            raise ValueError("previous chapter matches must be unique")

        scope_by_id = {
            chapter.chapter_id: chapter
            for chapter in self.request.scope.completed_chapters
        }
        for match in self.matches:
            allowed = scope_by_id.get(match.chapter_id)
            if allowed is None or allowed.chapter_no != match.chapter_no:
                raise ValueError(
                    "previous chapter match exceeds completed scope"
                )
            allowed_units = set(allowed.unit_ids)
            if any(
                excerpt.unit_id not in allowed_units
                for excerpt in match.excerpts
            ):
                raise ValueError(
                    "previous chapter excerpt exceeds completed scope"
                )

    @property
    def found(self) -> bool:
        return bool(self.matches)


@dataclass(frozen=True)
class VocabularyEncounter:
    """One stored representative vocabulary context from a completed unit."""

    book_id: str
    chapter_id: str
    chapter_no: int
    unit_id: str
    word: str
    normalized_word: str
    translation: str
    context: str
    pos: str = "other"
    encounter_count: int = 1
    mastered: bool = False
    first_seen_at: str = ""
    last_seen_at: str = ""

    def __post_init__(self) -> None:
        for field_name, value in (
            ("book_id", self.book_id),
            ("chapter_id", self.chapter_id),
            ("unit_id", self.unit_id),
            ("word", self.word),
            ("normalized_word", self.normalized_word),
            ("translation", self.translation),
            ("context", self.context),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        if self.chapter_no < 1:
            raise ValueError("chapter_no must be positive")
        if self.encounter_count < 1:
            raise ValueError("encounter_count must be positive")


@dataclass(frozen=True)
class VocabularyHistorySearchRequest:
    """Internal exact-lexeme query limited to completed prior chapters."""

    word: str
    language_id: str
    scope: PreviousReadingScope
    max_encounters: int = 5

    def __post_init__(self) -> None:
        if not self.word.strip():
            raise ValueError("word must not be empty")
        if not self.language_id.strip():
            raise ValueError("language_id must not be empty")
        if not 1 <= self.max_encounters <= 10:
            raise ValueError("max_encounters must be between 1 and 10")


@dataclass(frozen=True)
class VocabularyHistorySearchResult:
    """Chronological stored contexts used by the Agent to compare usage."""

    request: VocabularyHistorySearchRequest
    normalized_word: str
    encounters: tuple[VocabularyEncounter, ...] = ()
    truncated: bool = False

    def __post_init__(self) -> None:
        if not self.normalized_word.strip():
            raise ValueError("normalized_word must not be empty")
        if len(self.encounters) > self.request.max_encounters:
            raise ValueError("too many vocabulary encounters")
        chapter_numbers = [
            encounter.chapter_no for encounter in self.encounters
        ]
        if chapter_numbers != sorted(chapter_numbers):
            raise ValueError("vocabulary encounters must be chronological")

        allowed_units = {
            unit_id: (chapter.chapter_id, chapter.chapter_no)
            for chapter in self.request.scope.completed_chapters
            for unit_id in chapter.unit_ids
        }
        for encounter in self.encounters:
            if encounter.book_id != self.request.scope.book_id:
                raise ValueError(
                    "vocabulary encounter is from another book"
                )
            expected_chapter = allowed_units.get(encounter.unit_id)
            if expected_chapter is None:
                raise ValueError(
                    "vocabulary encounter exceeds completed scope"
                )
            if expected_chapter != (
                encounter.chapter_id,
                encounter.chapter_no,
            ):
                raise ValueError(
                    "vocabulary encounter has inconsistent chapter metadata"
                )
            if encounter.normalized_word != self.normalized_word:
                raise ValueError(
                    "vocabulary encounter has a different lexeme"
                )

    @property
    def found(self) -> bool:
        return bool(self.encounters)
