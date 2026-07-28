"""Tests for long-lived reading-companion and spoiler-safe search contracts."""

from dataclasses import FrozenInstanceError

import pytest

from superhp_agent.contracts import (
    ConversationMemory,
    ConversationMemoryKind,
    ConversationMemoryStatus,
    ReadingCompanionEpisode,
    ReadingCompanionEpisodeEndReason,
    ReadingCompanionEpisodeState,
    ReadingCompanionEpisodeTrigger,
    ReadingCompanionSession,
    ReadingCompanionSessionStatus,
    ReadingContextAccessScope,
    ReadingContextSearchRequest,
    ReadingContextSearchResult,
    ReadingContextSourceMatch,
    ReadingContextSummaryMatch,
)


def readable_scope() -> ReadingContextAccessScope:
    return ReadingContextAccessScope(
        book_id="book-1",
        current_chapter_id="chapter-3",
        readable_chapter_ids=("chapter-1", "chapter-2", "chapter-3"),
    )


def test_session_is_long_lived_and_separate_from_text_profile():
    session = ReadingCompanionSession(
        session_id="companion-1",
        reader_key="default",
        active_episode_id="episode-1",
    )

    assert session.status is ReadingCompanionSessionStatus.ACTIVE
    assert session.reader_key == "default"

    with pytest.raises(FrozenInstanceError):
        session.active_episode_id = "changed"


def test_archived_session_cannot_claim_an_active_episode():
    with pytest.raises(ValueError, match="archived session"):
        ReadingCompanionSession(
            session_id="companion-1",
            status=ReadingCompanionSessionStatus.ARCHIVED,
            active_episode_id="episode-1",
        )


def test_manual_reading_episode_freezes_the_invocation_context():
    episode = ReadingCompanionEpisode(
        episode_id="episode-1",
        session_id="companion-1",
        trigger=ReadingCompanionEpisodeTrigger.MANUAL_READING,
        start_message_id="message-10",
        book_id="book-1",
        chapter_id="chapter-3",
        selected_text="A short selected passage.",
    )

    assert episode.state is ReadingCompanionEpisodeState.ACTIVE
    assert episode.end_reason is None
    assert episode.chapter_id == "chapter-3"


def test_episode_lifecycle_requires_consistent_scope_and_end_metadata():
    with pytest.raises(ValueError, match="requires book_id and chapter_id"):
        ReadingCompanionEpisode(
            episode_id="episode",
            session_id="session",
            trigger=ReadingCompanionEpisodeTrigger.MANUAL_READING,
            start_message_id="message",
        )

    with pytest.raises(ValueError, match="selected_text requires chapter_id"):
        ReadingCompanionEpisode(
            episode_id="episode",
            session_id="session",
            trigger=ReadingCompanionEpisodeTrigger.USER_REQUEST,
            start_message_id="message",
            selected_text="orphan passage",
        )

    with pytest.raises(ValueError, match="active episode"):
        ReadingCompanionEpisode(
            episode_id="episode",
            session_id="session",
            trigger=ReadingCompanionEpisodeTrigger.ONBOARDING,
            start_message_id="message-1",
            end_message_id="message-2",
            end_reason=ReadingCompanionEpisodeEndReason.BOOK_SELECTED,
        )

    with pytest.raises(ValueError, match="requires end_message_id"):
        ReadingCompanionEpisode(
            episode_id="episode",
            session_id="session",
            trigger=ReadingCompanionEpisodeTrigger.ONBOARDING,
            start_message_id="message-1",
            state=ReadingCompanionEpisodeState.COMPLETED,
            end_reason=ReadingCompanionEpisodeEndReason.BOOK_SELECTED,
        )


def test_completed_episode_ends_one_task_without_archiving_session():
    session = ReadingCompanionSession(session_id="companion-1")
    episode = ReadingCompanionEpisode(
        episode_id="episode-1",
        session_id=session.session_id,
        trigger=ReadingCompanionEpisodeTrigger.ONBOARDING,
        start_message_id="message-1",
        state=ReadingCompanionEpisodeState.COMPLETED,
        end_message_id="message-8",
        end_reason=ReadingCompanionEpisodeEndReason.BOOK_SELECTED,
    )

    assert episode.state is ReadingCompanionEpisodeState.COMPLETED
    assert session.status is ReadingCompanionSessionStatus.ACTIVE


def test_conversation_memory_models_pending_ready_and_failed_revisions():
    pending = ConversationMemory(
        memory_id="memory-1",
        session_id="companion-1",
        episode_id="episode-1",
        kind=ConversationMemoryKind.EPISODE_SUMMARY,
        revision=1,
        source_start_message_id="message-1",
        source_end_message_id="message-8",
    )
    ready = ConversationMemory(
        memory_id="memory-2",
        session_id="companion-1",
        episode_id="episode-1",
        kind=ConversationMemoryKind.ROLLING_COMPACTION,
        revision=2,
        source_start_message_id="message-1",
        source_end_message_id="message-20",
        status=ConversationMemoryStatus.READY,
        summary="用户正在讨论第三章的人物关系。",
        input_tokens=1200,
        output_tokens=180,
    )
    failed = ConversationMemory(
        memory_id="memory-3",
        session_id="companion-1",
        episode_id="episode-1",
        kind=ConversationMemoryKind.EPISODE_SUMMARY,
        revision=1,
        source_start_message_id="message-1",
        source_end_message_id="message-8",
        status=ConversationMemoryStatus.FAILED,
        error_code="model_error",
    )

    assert pending.status is ConversationMemoryStatus.PENDING
    assert ready.summary.startswith("用户")
    assert failed.error_code == "model_error"


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (
            lambda: ConversationMemory(
                memory_id="memory",
                session_id="session",
                episode_id="episode",
                kind=ConversationMemoryKind.EPISODE_SUMMARY,
                revision=0,
                source_start_message_id="start",
                source_end_message_id="end",
            ),
            "revision",
        ),
        (
            lambda: ConversationMemory(
                memory_id="memory",
                session_id="session",
                episode_id="episode",
                kind=ConversationMemoryKind.EPISODE_SUMMARY,
                revision=1,
                source_start_message_id="start",
                source_end_message_id="end",
                status=ConversationMemoryStatus.READY,
            ),
            "requires summary",
        ),
        (
            lambda: ConversationMemory(
                memory_id="memory",
                session_id="session",
                episode_id="episode",
                kind=ConversationMemoryKind.EPISODE_SUMMARY,
                revision=1,
                source_start_message_id="start",
                source_end_message_id="end",
                status=ConversationMemoryStatus.PENDING,
                summary="not ready",
            ),
            "pending memory",
        ),
        (
            lambda: ConversationMemory(
                memory_id="memory",
                session_id="session",
                episode_id="episode",
                kind=ConversationMemoryKind.EPISODE_SUMMARY,
                revision=1,
                source_start_message_id="start",
                source_end_message_id="end",
                status=ConversationMemoryStatus.FAILED,
            ),
            "requires error_code",
        ),
        (
            lambda: ConversationMemory(
                memory_id="memory",
                session_id="session",
                episode_id="episode",
                kind=ConversationMemoryKind.EPISODE_SUMMARY,
                revision=1,
                source_start_message_id="start",
                source_end_message_id="end",
                status=ConversationMemoryStatus.FAILED,
                summary="partial summary must not be consumed",
                error_code="model_error",
            ),
            "must not contain summary",
        ),
    ],
)
def test_memory_rejects_inconsistent_generation_state(factory, message):
    with pytest.raises(ValueError, match=message):
        factory()


def test_reading_context_result_can_return_summary_and_source_together():
    request = ReadingContextSearchRequest(
        query="第三章里这两个人为什么争吵？",
        scope=readable_scope(),
    )
    result = ReadingContextSearchResult(
        request=request,
        summary_matches=(
            ReadingContextSummaryMatch(
                book_id="book-1",
                chapter_id="chapter-2",
                summary="两人在上一章已经产生分歧。",
            ),
        ),
        source_matches=(
            ReadingContextSourceMatch(
                book_id="book-1",
                chapter_id="chapter-3",
                unit_id="chapter-3-part-1",
                excerpt="They stopped at the doorway and argued.",
            ),
        ),
    )

    assert result.summary_matches[0].chapter_id == "chapter-2"
    assert result.source_matches[0].unit_id == "chapter-3-part-1"


@pytest.mark.parametrize(
    ("summary_match", "source_match", "message"),
    [
        (
            ReadingContextSummaryMatch(
                book_id="another-book",
                chapter_id="chapter-2",
                summary="Wrong book.",
            ),
            None,
            "another book",
        ),
        (
            ReadingContextSummaryMatch(
                book_id="book-1",
                chapter_id="chapter-4",
                summary="Future chapter.",
            ),
            None,
            "exceeds readable chapters",
        ),
        (
            None,
            ReadingContextSourceMatch(
                book_id="book-1",
                chapter_id="chapter-8",
                excerpt="A future spoiler.",
            ),
            "exceeds readable chapters",
        ),
    ],
)
def test_reading_context_result_rejects_spoilers_and_other_books(
    summary_match,
    source_match,
    message,
):
    with pytest.raises(ValueError, match=message):
        ReadingContextSearchResult(
            request=ReadingContextSearchRequest(
                query="What happens?",
                scope=readable_scope(),
            ),
            summary_matches=(summary_match,) if summary_match else (),
            source_matches=(source_match,) if source_match else (),
        )


def test_reading_context_scope_and_request_reject_invalid_boundaries():
    with pytest.raises(ValueError, match="must be readable"):
        ReadingContextAccessScope(
            book_id="book-1",
            current_chapter_id="chapter-3",
            readable_chapter_ids=("chapter-1", "chapter-2"),
        )

    with pytest.raises(ValueError, match="at least one source kind"):
        ReadingContextSearchRequest(
            query="人物关系",
            scope=readable_scope(),
            include_summaries=False,
            include_source=False,
        )

    with pytest.raises(ValueError, match="between 1 and 10"):
        ReadingContextSearchRequest(
            query="人物关系",
            scope=readable_scope(),
            limit_per_kind=11,
        )
