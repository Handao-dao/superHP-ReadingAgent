"""Tests for durable reading companion coordination."""

from dataclasses import replace

import pytest

from superhp_agent.application import (
    ReadingCompanionSessionConflictError,
    ReadingCompanionSessionCoordinator,
    ReadingCompanionSessionNotFoundError,
)
from superhp_agent.contracts import (
    ConversationMemory,
    ConversationMemoryKind,
    ConversationMemoryStatus,
    ReadingCompanionEpisode,
    ReadingCompanionEpisodeTrigger,
    ReadingCompanionMessage,
    ReadingCompanionMessageRole,
    ReadingCompanionReply,
    ReadingCompanionRunState,
)
from superhp_agent.storage import AppDB


class FakeManualRunner:
    def __init__(self):
        self.started = []
        self.run_calls = []

    def start(
        self,
        *,
        session_id,
        current_unit_id,
        user_message,
        selected_text="",
    ):
        self.started.append(
            (
                session_id,
                current_unit_id,
                user_message,
                selected_text,
            )
        )
        return _state(
            session_id=session_id,
            messages=(("user", user_message),),
            selected_text=selected_text,
            episode_id=f"{session_id}-episode-{len(self.started)}",
        )

    async def run(
        self,
        state,
        *,
        user_message=None,
        conversation_memory="",
    ):
        self.run_calls.append((state, user_message, conversation_memory))
        conversation = list(state.conversation)
        if user_message is not None:
            conversation.append(
                _message(state, "user", user_message, len(conversation))
            )
        content = f"回答 {len(self.run_calls)}"
        conversation.append(
            _message(state, "assistant", content, len(conversation))
        )
        next_state = replace(state, conversation=tuple(conversation))
        return ReadingCompanionReply(state=next_state, message=content)


class FakeMemoryGenerator:
    def __init__(self):
        self.calls = []

    async def generate(self, state, *, kind):
        self.calls.append((state, kind))
        return ConversationMemory(
            memory_id=f"{state.episode.session_id}-memory",
            session_id=state.episode.session_id,
            episode_id=state.episode.episode_id,
            kind=kind,
            revision=1,
            source_start_message_id=state.conversation[0].message_id,
            source_end_message_id=state.conversation[-1].message_id,
            status=ConversationMemoryStatus.READY,
            summary="本轮摘要",
        )

    def context_for_session(self, session_id, *, episode_id=""):
        del episode_id
        return f"{session_id} 的既有摘要"

    async def compact_if_needed(self, state, *, policy):
        del policy
        return state


def _coordinator(runner, db, memory_generator=None):
    return ReadingCompanionSessionCoordinator(
        runner,
        db.reading_companion_repository,
        memory_generator or FakeMemoryGenerator(),
    )


def _message(state, role, content, index):
    return ReadingCompanionMessage(
        message_id=f"{state.episode.episode_id}-message-{index}",
        session_id=state.episode.session_id,
        episode_id=state.episode.episode_id,
        role=ReadingCompanionMessageRole(role),
        content=content,
    )


def _state(
    *,
    session_id="session-1",
    messages=(("user", "问题"),),
    selected_text="",
    episode_id=None,
):
    episode_id = episode_id or f"{session_id}-episode"
    conversation = tuple(
        ReadingCompanionMessage(
            message_id=f"{episode_id}-message-{index}",
            session_id=session_id,
            episode_id=episode_id,
            role=ReadingCompanionMessageRole(role),
            content=content,
        )
        for index, (role, content) in enumerate(messages)
    )
    return ReadingCompanionRunState(
        episode=ReadingCompanionEpisode(
            episode_id=episode_id,
            session_id=session_id,
            trigger=ReadingCompanionEpisodeTrigger.MANUAL_READING,
            start_message_id=conversation[0].message_id,
            book_id="book-1",
            chapter_id="chapter-2",
            unit_id="unit-2",
            selected_text=selected_text,
        ),
        conversation=conversation,
    )


@pytest.mark.asyncio
async def test_coordinator_starts_resumes_retries_and_loads_state(tmp_path):
    db = AppDB(tmp_path / "app.db")
    try:
        runner = FakeManualRunner()
        coordinator = _coordinator(runner, db)

        started = await coordinator.start(
            session_id="session-1",
            current_unit_id="unit-2",
            user_message="他以前出现过吗？",
            selected_text="Mr. Gray",
        )
        resumed = await coordinator.resume(
            "session-1",
            user_message="第一次是在哪里？",
        )
        retried = await coordinator.retry("session-1")

        assert runner.started == [
            ("session-1", "unit-2", "他以前出现过吗？", "Mr. Gray")
        ]
        assert [call[1] for call in runner.run_calls] == [
            None,
            "第一次是在哪里？",
            None,
        ]
        assert all(
            call[2] == "session-1 的既有摘要"
            for call in runner.run_calls
        )
        assert started.state.conversation[-1].content == "回答 1"
        assert resumed.state.conversation[-1].content == "回答 2"
        assert retried.state.conversation[-1].content == "回答 3"
        assert coordinator.load("session-1") == retried.state
    finally:
        db.close()


@pytest.mark.asyncio
async def test_coordinator_restores_state_in_a_new_process_boundary(tmp_path):
    db_path = tmp_path / "app.db"
    first_db = AppDB(db_path)
    first_runner = FakeManualRunner()
    first = _coordinator(first_runner, first_db)
    await first.start(
        session_id="session-1",
        current_unit_id="unit-2",
        user_message="问题",
    )
    first_db.close()

    second_db = AppDB(db_path)
    try:
        second_runner = FakeManualRunner()
        second = _coordinator(second_runner, second_db)
        restored = second.load("session-1")
        resumed = await second.resume("session-1", user_message="继续")

        assert restored is not None
        assert [item.content for item in restored.conversation] == [
            "问题",
            "回答 1",
        ]
        assert resumed.state.conversation[-2].content == "继续"
    finally:
        second_db.close()


@pytest.mark.asyncio
async def test_coordinator_rejects_duplicate_and_unknown_sessions(tmp_path):
    db = AppDB(tmp_path / "app.db")
    try:
        coordinator = _coordinator(FakeManualRunner(), db)
        await coordinator.start(
            session_id="session-1",
            current_unit_id="unit-2",
            user_message="问题",
        )

        with pytest.raises(ReadingCompanionSessionConflictError):
            await coordinator.start(
                session_id="session-1",
                current_unit_id="unit-2",
                user_message="另一个问题",
            )
        with pytest.raises(ReadingCompanionSessionNotFoundError):
            await coordinator.resume("missing", user_message="问题")
        with pytest.raises(ReadingCompanionSessionNotFoundError):
            await coordinator.retry("missing")
    finally:
        db.close()


@pytest.mark.asyncio
async def test_coordinator_generates_session_id_when_caller_omits_it(
    tmp_path,
):
    db = AppDB(tmp_path / "app.db")
    try:
        runner = FakeManualRunner()
        coordinator = _coordinator(runner, db)

        reply = await coordinator.start(
            current_unit_id="unit-2",
            user_message="问题",
        )

        session_id = reply.state.episode.session_id
        assert session_id
        assert coordinator.load(session_id) == reply.state
    finally:
        db.close()


@pytest.mark.asyncio
async def test_coordinator_closes_episode_before_generating_summary(
    tmp_path,
):
    db = AppDB(tmp_path / "app.db")
    try:
        memory_generator = FakeMemoryGenerator()
        coordinator = _coordinator(
            FakeManualRunner(),
            db,
            memory_generator,
        )
        await coordinator.start(
            session_id="session-1",
            current_unit_id="unit-2",
            user_message="问题",
        )

        memory = await coordinator.end("session-1")

        assert memory.kind is ConversationMemoryKind.EPISODE_SUMMARY
        assert db.reading_companion_repository.load_active_run(
            "session-1"
        ) is None
        assert (
            db.reading_companion_repository.load_session(
                "session-1"
            ).active_episode_id
            == ""
        )
        assert len(memory_generator.calls) == 1
    finally:
        db.close()


@pytest.mark.asyncio
async def test_closed_session_can_start_a_new_episode_with_same_identity(
    tmp_path,
):
    db = AppDB(tmp_path / "app.db")
    try:
        coordinator = _coordinator(FakeManualRunner(), db)
        first = await coordinator.start(
            session_id="session-1",
            current_unit_id="unit-2",
            user_message="第一轮",
        )
        await coordinator.end("session-1")

        second = await coordinator.start(
            session_id="session-1",
            current_unit_id="unit-2",
            user_message="第二轮",
        )

        assert first.state.episode.episode_id != (
            second.state.episode.episode_id
        )
        assert second.state.episode.session_id == "session-1"
    finally:
        db.close()
