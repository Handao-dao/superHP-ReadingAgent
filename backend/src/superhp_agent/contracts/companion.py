"""Stable boundaries for the future long-lived reading companion.

These immutable contracts describe session and episode lifecycles, compressed
conversation memory, and spoiler-safe reading-context search. They do not
persist messages, generate summaries, search corpus files, or call a model.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


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
        if self.selected_text and not self.chapter_id:
            raise ValueError("selected_text requires chapter_id")
        if self.trigger is ReadingCompanionEpisodeTrigger.MANUAL_READING:
            if not self.book_id or not self.chapter_id:
                raise ValueError(
                    "manual_reading episode requires book_id and chapter_id"
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
class ReadingContextAccessScope:
    """Trusted spoiler boundary supplied by the application, not the model."""

    book_id: str
    current_chapter_id: str
    readable_chapter_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.book_id.strip():
            raise ValueError("book_id must not be empty")
        if not self.current_chapter_id.strip():
            raise ValueError("current_chapter_id must not be empty")
        if not self.readable_chapter_ids:
            raise ValueError("readable_chapter_ids must not be empty")
        if any(
            not chapter_id.strip()
            for chapter_id in self.readable_chapter_ids
        ):
            raise ValueError(
                "readable_chapter_ids must contain non-empty values"
            )
        if len(set(self.readable_chapter_ids)) != len(
            self.readable_chapter_ids
        ):
            raise ValueError("readable_chapter_ids must be unique")
        if self.current_chapter_id not in self.readable_chapter_ids:
            raise ValueError("current_chapter_id must be readable")


@dataclass(frozen=True)
class ReadingContextSearchRequest:
    """Internal request combining model intent with a trusted access scope."""

    query: str
    scope: ReadingContextAccessScope
    include_summaries: bool = True
    include_source: bool = True
    limit_per_kind: int = 3

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise ValueError("query must not be empty")
        if not self.include_summaries and not self.include_source:
            raise ValueError(
                "reading context search requires at least one source kind"
            )
        if not 1 <= self.limit_per_kind <= 10:
            raise ValueError("limit_per_kind must be between 1 and 10")


@dataclass(frozen=True)
class ReadingContextSummaryMatch:
    """One chapter summary found inside the trusted reading range."""

    book_id: str
    chapter_id: str
    summary: str

    def __post_init__(self) -> None:
        if not self.book_id.strip():
            raise ValueError("summary match book_id must not be empty")
        if not self.chapter_id.strip():
            raise ValueError("summary match chapter_id must not be empty")
        if not self.summary.strip():
            raise ValueError("summary match must not be empty")


@dataclass(frozen=True)
class ReadingContextSourceMatch:
    """One source-text excerpt found inside the trusted reading range."""

    book_id: str
    chapter_id: str
    excerpt: str
    unit_id: str = ""

    def __post_init__(self) -> None:
        if not self.book_id.strip():
            raise ValueError("source match book_id must not be empty")
        if not self.chapter_id.strip():
            raise ValueError("source match chapter_id must not be empty")
        if not self.excerpt.strip():
            raise ValueError("source match excerpt must not be empty")


@dataclass(frozen=True)
class ReadingContextSearchResult:
    """Spoiler-safe summary and source matches returned to the Agent tool."""

    request: ReadingContextSearchRequest
    summary_matches: tuple[ReadingContextSummaryMatch, ...] = ()
    source_matches: tuple[ReadingContextSourceMatch, ...] = ()

    def __post_init__(self) -> None:
        if not self.request.include_summaries and self.summary_matches:
            raise ValueError("summary matches were not requested")
        if not self.request.include_source and self.source_matches:
            raise ValueError("source matches were not requested")
        if len(self.summary_matches) > self.request.limit_per_kind:
            raise ValueError("too many summary matches")
        if len(self.source_matches) > self.request.limit_per_kind:
            raise ValueError("too many source matches")

        scope = self.request.scope
        for match in (*self.summary_matches, *self.source_matches):
            if match.book_id != scope.book_id:
                raise ValueError("reading context match is from another book")
            if match.chapter_id not in scope.readable_chapter_ids:
                raise ValueError(
                    "reading context match exceeds readable chapters"
                )
