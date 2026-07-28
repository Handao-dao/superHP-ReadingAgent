"""Tests for long-lived reading-companion and spoiler-safe search contracts."""

from dataclasses import FrozenInstanceError

import pytest

from superhp_agent.contracts import (
    AgentToolExecutionContext,
    CompletedChapterScope,
    ConversationMemory,
    ConversationMemoryKind,
    ConversationMemoryStatus,
    PreviousChapterExcerpt,
    PreviousChapterMatch,
    PreviousChapterSearchRequest,
    PreviousChapterSearchResult,
    PreviousReadingScope,
    ReadingCompanionEpisode,
    ReadingCompanionEpisodeEndReason,
    ReadingCompanionEpisodeState,
    ReadingCompanionEpisodeTrigger,
    ReadingCompanionSession,
    ReadingCompanionSessionStatus,
    VocabularyEncounter,
    VocabularyHistorySearchRequest,
    VocabularyHistorySearchResult,
)


def previous_scope() -> PreviousReadingScope:
    return PreviousReadingScope(
        book_id="book-1",
        current_chapter_id="chapter-4",
        current_chapter_no=4,
        completed_chapters=(
            CompletedChapterScope(
                chapter_id="chapter-1",
                chapter_no=1,
                unit_ids=("chapter-1",),
            ),
            CompletedChapterScope(
                chapter_id="chapter-2",
                chapter_no=2,
                unit_ids=("chapter-2-a", "chapter-2-b"),
            ),
        ),
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


def test_previous_reading_scope_contains_only_checkpointed_prior_units():
    scope = previous_scope()
    context = AgentToolExecutionContext(
        session_id="session-1",
        episode_id="episode-1",
        previous_reading_scope=scope,
    )

    assert scope.searchable_unit_ids == (
        "chapter-1",
        "chapter-2-a",
        "chapter-2-b",
    )
    assert context.previous_reading_scope == scope


def test_previous_chapter_result_groups_summary_and_source_evidence():
    request = PreviousChapterSearchRequest(
        query="Snape",
        scope=previous_scope(),
    )
    result = PreviousChapterSearchResult(
        request=request,
        matches=(
            PreviousChapterMatch(
                chapter_id="chapter-2",
                chapter_no=2,
                chapter_title="The Second Chapter",
                summary="Snape appeared during the feast.",
                excerpts=(
                    PreviousChapterExcerpt(
                        unit_id="chapter-2-a",
                        text="Professor Snape looked across the hall.",
                    ),
                ),
            ),
        ),
    )

    assert result.found is True
    assert result.matches[0].summary.startswith("Snape")
    assert result.matches[0].excerpts[0].unit_id == "chapter-2-a"


@pytest.mark.parametrize(
    ("match", "message"),
    [
        (
            PreviousChapterMatch(
                chapter_id="chapter-4",
                chapter_no=4,
                chapter_title="Current Chapter",
                summary="Current chapter must not be searchable.",
            ),
            "exceeds completed scope",
        ),
        (
            PreviousChapterMatch(
                chapter_id="chapter-2",
                chapter_no=2,
                chapter_title="The Second Chapter",
                excerpts=(
                    PreviousChapterExcerpt(
                        unit_id="chapter-2-future",
                        text="This unit was not checkpointed.",
                    ),
                ),
            ),
            "excerpt exceeds completed scope",
        ),
    ],
)
def test_previous_chapter_result_rejects_current_or_uncheckpointed_content(
    match,
    message,
):
    with pytest.raises(ValueError, match=message):
        PreviousChapterSearchResult(
            request=PreviousChapterSearchRequest(
                query="Snape",
                scope=previous_scope(),
            ),
            matches=(match,),
        )


def test_previous_reading_scope_rejects_current_or_future_chapters():
    with pytest.raises(ValueError, match="current chapter"):
        PreviousReadingScope(
            book_id="book-1",
            current_chapter_id="chapter-3",
            current_chapter_no=3,
            completed_chapters=(
                CompletedChapterScope(
                    chapter_id="chapter-3",
                    chapter_no=3,
                    unit_ids=("chapter-3",),
                ),
            ),
        )

    with pytest.raises(ValueError, match="between 1 and 10"):
        PreviousChapterSearchRequest(
            query="人物关系",
            scope=previous_scope(),
            max_chapters=11,
        )


def test_vocabulary_history_result_compares_recorded_prior_contexts():
    request = VocabularyHistorySearchRequest(
        word="charge",
        language_id="en",
        scope=previous_scope(),
    )
    result = VocabularyHistorySearchResult(
        request=request,
        normalized_word="charge",
        encounters=(
            VocabularyEncounter(
                book_id="book-1",
                chapter_id="chapter-1",
                chapter_no=1,
                unit_id="chapter-1",
                word="charge",
                normalized_word="charge",
                translation="收费",
                context="The hotel charged him ten pounds.",
                pos="verb",
            ),
            VocabularyEncounter(
                book_id="book-1",
                chapter_id="chapter-2",
                chapter_no=2,
                unit_id="chapter-2-b",
                word="charge",
                normalized_word="charge",
                translation="指控",
                context="He was charged with theft.",
                pos="verb",
                encounter_count=2,
            ),
        ),
    )

    assert result.found is True
    assert [item.translation for item in result.encounters] == [
        "收费",
        "指控",
    ]


@pytest.mark.parametrize(
    ("encounter", "message"),
    [
        (
            VocabularyEncounter(
                book_id="another-book",
                chapter_id="chapter-1",
                chapter_no=1,
                unit_id="chapter-1",
                word="charge",
                normalized_word="charge",
                translation="收费",
                context="A stored context.",
            ),
            "another book",
        ),
        (
            VocabularyEncounter(
                book_id="book-1",
                chapter_id="chapter-4",
                chapter_no=4,
                unit_id="chapter-4",
                word="charge",
                normalized_word="charge",
                translation="冲锋",
                context="An unread context.",
            ),
            "exceeds completed scope",
        ),
        (
            VocabularyEncounter(
                book_id="book-1",
                chapter_id="chapter-1",
                chapter_no=1,
                unit_id="chapter-1",
                word="charged",
                normalized_word="charged",
                translation="收费",
                context="A different stored lexeme.",
            ),
            "different lexeme",
        ),
        (
            VocabularyEncounter(
                book_id="book-1",
                chapter_id="chapter-2",
                chapter_no=2,
                unit_id="chapter-1",
                word="charge",
                normalized_word="charge",
                translation="收费",
                context="A context with inconsistent chapter metadata.",
            ),
            "inconsistent chapter metadata",
        ),
    ],
)
def test_vocabulary_history_rejects_other_books_unread_units_and_lexemes(
    encounter,
    message,
):
    with pytest.raises(ValueError, match=message):
        VocabularyHistorySearchResult(
            request=VocabularyHistorySearchRequest(
                word="charge",
                language_id="en",
                scope=previous_scope(),
            ),
            normalized_word="charge",
            encounters=(encounter,),
        )
