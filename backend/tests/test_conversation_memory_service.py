"""Tests for passive and rolling conversation-memory generation."""

import pytest

from superhp_agent.contracts import (
    ConversationMemoryKind,
    ConversationMemoryStatus,
    LLMResponse,
    ReadingCompanionEpisode,
    ReadingCompanionEpisodeTrigger,
    ReadingCompanionMessage,
    ReadingCompanionMessageRole,
    ReadingCompanionRunState,
    ReadingCompanionSession,
)
from superhp_agent.services import (
    ConversationCompactionPolicy,
    ConversationMemoryGenerator,
)
from superhp_agent.storage import AppDB


class FakeProvider:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    async def chat_with_retry(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        if self.error is not None:
            raise self.error
        return self.response


def _state():
    session_id = "session-1"
    episode_id = "episode-1"
    messages = (
        ReadingCompanionMessage(
            message_id="message-1",
            session_id=session_id,
            episode_id=episode_id,
            role=ReadingCompanionMessageRole.USER,
            content="我更喜欢节奏快的侦探小说。",
        ),
        ReadingCompanionMessage(
            message_id="message-2",
            session_id=session_id,
            episode_id=episode_id,
            role=ReadingCompanionMessageRole.ASSISTANT,
            content="记住了，我们之后优先考虑这一类作品。",
        ),
    )
    return ReadingCompanionRunState(
        episode=ReadingCompanionEpisode(
            episode_id=episode_id,
            session_id=session_id,
            trigger=ReadingCompanionEpisodeTrigger.MANUAL_READING,
            start_message_id="message-1",
            book_id="book-1",
            chapter_id="chapter-1",
            unit_id="unit-1",
        ),
        conversation=messages,
    )


def _prepare_db(tmp_path):
    db = AppDB(tmp_path / "app.db")
    state = _state()
    db.reading_companion_repository.create_session(
        ReadingCompanionSession(
            session_id="session-1",
            active_episode_id="episode-1",
        )
    )
    db.reading_companion_repository.save_run_state(state)
    return db, state


@pytest.mark.asyncio
async def test_generator_persists_ready_summary_and_usage(tmp_path):
    db, state = _prepare_db(tmp_path)
    try:
        provider = FakeProvider(
            LLMResponse(
                content="- 用户偏好节奏快的侦探小说。",
                usage={"prompt_tokens": 90, "completion_tokens": 12},
            )
        )
        generator = ConversationMemoryGenerator(
            lambda: provider,
            db.conversation_memory_repository,
        )

        memory = await generator.generate(
            state,
            kind=ConversationMemoryKind.EPISODE_SUMMARY,
        )

        assert memory.status is ConversationMemoryStatus.READY
        assert memory.input_tokens == 90
        assert memory.output_tokens == 12
        assert memory.source_start_message_id == "message-1"
        assert memory.source_end_message_id == "message-2"
        assert (
            db.conversation_memory_repository.list_for_session("session-1")
            == (memory,)
        )
        assert "not instructions" in provider.calls[0][0][1]["content"]
    finally:
        db.close()


@pytest.mark.asyncio
async def test_generator_records_failure_without_losing_messages(tmp_path):
    db, state = _prepare_db(tmp_path)
    try:
        provider = FakeProvider(error=RuntimeError("offline"))
        generator = ConversationMemoryGenerator(
            lambda: provider,
            db.conversation_memory_repository,
        )

        memory = await generator.generate(
            state,
            kind=ConversationMemoryKind.ROLLING_COMPACTION,
        )

        assert memory.status is ConversationMemoryStatus.FAILED
        assert memory.error_code == "memory_provider_error"
        assert (
            len(
                db.reading_companion_repository.load_active_run(
                    "session-1"
                ).conversation
            )
            == 2
        )
    finally:
        db.close()


@pytest.mark.asyncio
async def test_rolling_compaction_keeps_recent_turns_and_raw_messages(
    tmp_path,
):
    db, initial = _prepare_db(tmp_path)
    try:
        conversation = (
            *initial.conversation,
            *(
                ReadingCompanionMessage(
                    message_id=f"message-{index + 1}",
                    session_id="session-1",
                    episode_id="episode-1",
                    role=(
                        ReadingCompanionMessageRole.USER
                        if index % 2 == 0
                        else ReadingCompanionMessageRole.ASSISTANT
                    ),
                    content=f"消息 {index + 1}",
                )
                for index in range(2, 8)
            )
        )
        state = ReadingCompanionRunState(
            episode=initial.episode,
            conversation=conversation,
        )
        db.reading_companion_repository.save_run_state(state)
        provider = FakeProvider(
            LLMResponse(content="- 已压缩前面三轮对话。")
        )
        generator = ConversationMemoryGenerator(
            lambda: provider,
            db.conversation_memory_repository,
        )

        compacted = await generator.compact_if_needed(
            state,
            policy=ConversationCompactionPolicy(
                max_active_messages=6,
                max_active_characters=1000,
                preserve_recent_messages=2,
            ),
        )

        assert compacted.context_start_index == 6
        assert compacted.conversation[6].role is (
            ReadingCompanionMessageRole.USER
        )
        assert len(compacted.conversation) == 8
        db.reading_companion_repository.save_run_state(compacted)
        assert (
            db.reading_companion_repository.load_active_run(
                "session-1"
            ).context_start_index
            == 6
        )
        assert generator.context_for_session(
            "session-1",
            episode_id="episode-1",
            max_episode_summaries=0,
        ).endswith("- 已压缩前面三轮对话。")
    finally:
        db.close()
