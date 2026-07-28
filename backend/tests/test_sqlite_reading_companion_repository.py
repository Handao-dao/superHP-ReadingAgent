"""Round-trip tests for durable companion transcripts and memories."""

from dataclasses import replace

import pytest

from superhp_agent.contracts import (
    ConversationMemory,
    ConversationMemoryKind,
    ConversationMemoryStatus,
    LLMToolCall,
    ReadingCompanionEpisode,
    ReadingCompanionEpisodeEndReason,
    ReadingCompanionEpisodeState,
    ReadingCompanionEpisodeTrigger,
    ReadingCompanionMessage,
    ReadingCompanionMessageRole,
    ReadingCompanionRunState,
    ReadingCompanionSession,
)
from superhp_agent.ports.repositories import (
    ConversationMemoryRepository,
    ReadingCompanionRepository,
)
from superhp_agent.storage import AppDB


def _state() -> ReadingCompanionRunState:
    session_id = "session-1"
    episode_id = "episode-1"
    tool_call = LLMToolCall(
        id="call-1",
        name="search_previous_chapters",
        arguments={"query": "Gray"},
        raw_arguments='{"query":"Gray"}',
    )
    conversation = (
        ReadingCompanionMessage(
            message_id="message-1",
            session_id=session_id,
            episode_id=episode_id,
            role=ReadingCompanionMessageRole.USER,
            content="他以前出现过吗？",
        ),
        ReadingCompanionMessage(
            message_id="message-2",
            session_id=session_id,
            episode_id=episode_id,
            role=ReadingCompanionMessageRole.ASSISTANT,
            tool_calls=(tool_call,),
        ),
        ReadingCompanionMessage(
            message_id="message-3",
            session_id=session_id,
            episode_id=episode_id,
            role=ReadingCompanionMessageRole.TOOL,
            content='{"ok":true}',
            tool_call_id="call-1",
            tool_name="search_previous_chapters",
        ),
        ReadingCompanionMessage(
            message_id="message-4",
            session_id=session_id,
            episode_id=episode_id,
            role=ReadingCompanionMessageRole.ASSISTANT,
            content="他在上一章出现过。",
        ),
    )
    return ReadingCompanionRunState(
        episode=ReadingCompanionEpisode(
            episode_id=episode_id,
            session_id=session_id,
            trigger=ReadingCompanionEpisodeTrigger.MANUAL_READING,
            start_message_id="message-1",
            book_id="book-1",
            chapter_id="chapter-2",
            unit_id="unit-2",
            selected_text="Mr. Gray",
        ),
        conversation=conversation,
        tool_call_count=1,
    )


def test_repository_ports_are_satisfied(tmp_path):
    db = AppDB(tmp_path / "app.db")
    try:
        assert isinstance(
            db.reading_companion_repository,
            ReadingCompanionRepository,
        )
        assert isinstance(
            db.conversation_memory_repository,
            ConversationMemoryRepository,
        )
    finally:
        db.close()


def test_run_state_round_trips_with_native_tool_messages(tmp_path):
    db = AppDB(tmp_path / "app.db")
    try:
        repository = db.reading_companion_repository
        repository.create_session(
            ReadingCompanionSession(
                session_id="session-1",
                active_episode_id="episode-1",
            )
        )
        state = _state()

        repository.save_run_state(state)
        restored = repository.load_active_run("session-1")

        assert restored == replace(
            state,
            episode=replace(
                state.episode,
                created_at=restored.episode.created_at,
            ),
        )
        assert restored.conversation[1].tool_calls[0].arguments == {
            "query": "Gray"
        }
        assert repository.load_session("session-1").created_at
    finally:
        db.close()


def test_old_messages_cannot_be_rewritten(tmp_path):
    db = AppDB(tmp_path / "app.db")
    try:
        repository = db.reading_companion_repository
        repository.create_session(
            ReadingCompanionSession(
                session_id="session-1",
                active_episode_id="episode-1",
            )
        )
        state = _state()
        repository.save_run_state(state)
        changed_first = replace(
            state.conversation[0],
            content="被改写的原始问题",
        )

        with pytest.raises(ValueError, match="cannot be rewritten"):
            repository.save_run_state(
                replace(
                    state,
                    conversation=(changed_first, *state.conversation[1:]),
                )
            )
    finally:
        db.close()


def test_closing_episode_clears_only_the_active_pointer(tmp_path):
    db = AppDB(tmp_path / "app.db")
    try:
        repository = db.reading_companion_repository
        repository.create_session(
            ReadingCompanionSession(
                session_id="session-1",
                active_episode_id="episode-1",
            )
        )
        state = _state()
        repository.save_run_state(state)
        repository.close_active_episode(
            replace(
                state.episode,
                state=ReadingCompanionEpisodeState.COMPLETED,
                end_message_id="message-4",
                end_reason=ReadingCompanionEpisodeEndReason.USER_ENDED,
                ended_at="2026-07-28T16:00:00+08:00",
            )
        )

        assert repository.load_active_run("session-1") is None
        assert repository.load_session("session-1").active_episode_id == ""
        row = db.database.connection.execute(
            """
            SELECT state, end_reason, end_message_id
            FROM reading_companion_episodes
            WHERE episode_id = 'episode-1'
            """
        ).fetchone()
        assert tuple(row) == ("completed", "user_ended", "message-4")
        assert (
            db.database.connection.execute(
                "SELECT COUNT(*) FROM reading_companion_messages"
            ).fetchone()[0]
            == 4
        )
    finally:
        db.close()


def test_memory_advances_from_pending_and_keeps_revisions(tmp_path):
    db = AppDB(tmp_path / "app.db")
    try:
        run_repository = db.reading_companion_repository
        memory_repository = db.conversation_memory_repository
        run_repository.create_session(
            ReadingCompanionSession(
                session_id="session-1",
                active_episode_id="episode-1",
            )
        )
        run_repository.save_run_state(_state())
        pending = ConversationMemory(
            memory_id="memory-1",
            session_id="session-1",
            episode_id="episode-1",
            kind=ConversationMemoryKind.ROLLING_COMPACTION,
            revision=1,
            source_start_message_id="message-1",
            source_end_message_id="message-3",
        )
        memory_repository.save(pending)
        stored_pending = memory_repository.list_for_session("session-1")[0]
        ready = replace(
            stored_pending,
            status=ConversationMemoryStatus.READY,
            summary="用户询问 Gray 是否在前文出现。",
            input_tokens=120,
            output_tokens=18,
        )

        memory_repository.save(ready)

        assert memory_repository.list_for_session(
            "session-1",
            kind=ConversationMemoryKind.ROLLING_COMPACTION,
        ) == (ready,)
        assert memory_repository.next_revision(
            "session-1",
            ConversationMemoryKind.ROLLING_COMPACTION,
        ) == 2
        with pytest.raises(ValueError, match="immutable"):
            memory_repository.save(
                replace(ready, summary="试图覆盖既有摘要")
            )
    finally:
        db.close()
