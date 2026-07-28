"""Tests for durable reading companion coordination."""

from dataclasses import replace

import pytest

from superhp_agent.application import (
    ReadingCompanionSessionConflictError,
    ReadingCompanionSessionCoordinator,
    ReadingCompanionSessionNotFoundError,
)
from superhp_agent.contracts import (
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
        )

    async def run(self, state, *, user_message=None):
        self.run_calls.append((state, user_message))
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


def _message(state, role, content, index):
    return ReadingCompanionMessage(
        message_id=f"{state.episode.session_id}-message-{index}",
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
):
    episode_id = f"{session_id}-episode"
    conversation = tuple(
        ReadingCompanionMessage(
            message_id=f"{session_id}-message-{index}",
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
        coordinator = ReadingCompanionSessionCoordinator(
            runner,
            db.reading_companion_repository,
        )

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
    first = ReadingCompanionSessionCoordinator(
        first_runner,
        first_db.reading_companion_repository,
    )
    await first.start(
        session_id="session-1",
        current_unit_id="unit-2",
        user_message="问题",
    )
    first_db.close()

    second_db = AppDB(db_path)
    try:
        second_runner = FakeManualRunner()
        second = ReadingCompanionSessionCoordinator(
            second_runner,
            second_db.reading_companion_repository,
        )
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
        coordinator = ReadingCompanionSessionCoordinator(
            FakeManualRunner(),
            db.reading_companion_repository,
        )
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
        coordinator = ReadingCompanionSessionCoordinator(
            runner,
            db.reading_companion_repository,
        )

        reply = await coordinator.start(
            current_unit_id="unit-2",
            user_message="问题",
        )

        session_id = reply.state.episode.session_id
        assert session_id
        assert coordinator.load(session_id) == reply.state
    finally:
        db.close()
