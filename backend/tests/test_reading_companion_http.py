"""HTTP contract tests for manual reading-companion conversations."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from superhp_agent.agents import ReadingCompanionStateError
from superhp_agent.application import (
    ManualReadingCompanionError,
    ReadingCompanionSessionConflictError,
    ReadingCompanionSessionNotFoundError,
)
from superhp_agent.contracts import (
    LLMToolCall,
    ReadingCompanionEpisode,
    ReadingCompanionEpisodeTrigger,
    ReadingCompanionMessage,
    ReadingCompanionMessageRole,
    ReadingCompanionReply,
    ReadingCompanionRunState,
)
from superhp_agent.transport.reading_companion_http import (
    create_reading_companion_router,
)


class FakeCoordinator:
    def __init__(self):
        self.states = {}
        self.started = None
        self.resumed = None
        self.retried = None
        self.start_error = None
        self.resume_error = None
        self.retry_error = None

    async def start(self, **kwargs):
        if self.start_error:
            raise self.start_error
        self.started = kwargs
        state = _public_state(kwargs.get("session_id") or "generated-session")
        self.states[state.episode.session_id] = state
        return ReadingCompanionReply(state=state, message="回答")

    async def resume(self, session_id, *, user_message):
        if self.resume_error:
            raise self.resume_error
        self.resumed = (session_id, user_message)
        state = _public_state(session_id, final_answer="继续回答")
        self.states[session_id] = state
        return ReadingCompanionReply(state=state, message="继续回答")

    async def retry(self, session_id):
        if self.retry_error:
            raise self.retry_error
        self.retried = session_id
        state = _public_state(session_id, final_answer="重试成功")
        self.states[session_id] = state
        return ReadingCompanionReply(state=state, message="重试成功")

    def load(self, session_id):
        return self.states.get(session_id)


def _public_state(session_id="session-1", *, final_answer="回答"):
    episode_id = f"{session_id}-episode"
    tool_call = LLMToolCall(
        id="search-1",
        name="search_previous_chapters",
        arguments={"query": "Mr. Gray"},
    )
    messages = (
        ReadingCompanionMessage(
            message_id="user-1",
            session_id=session_id,
            episode_id=episode_id,
            role=ReadingCompanionMessageRole.USER,
            content="他以前出现过吗？",
        ),
        ReadingCompanionMessage(
            message_id="assistant-tool",
            session_id=session_id,
            episode_id=episode_id,
            role=ReadingCompanionMessageRole.ASSISTANT,
            tool_calls=(tool_call,),
        ),
        ReadingCompanionMessage(
            message_id="tool-1",
            session_id=session_id,
            episode_id=episode_id,
            role=ReadingCompanionMessageRole.TOOL,
            content='{"ok": true}',
            tool_call_id="search-1",
            tool_name="search_previous_chapters",
        ),
        ReadingCompanionMessage(
            message_id="assistant-1",
            session_id=session_id,
            episode_id=episode_id,
            role=ReadingCompanionMessageRole.ASSISTANT,
            content=final_answer,
        ),
    )
    return ReadingCompanionRunState(
        episode=ReadingCompanionEpisode(
            episode_id=episode_id,
            session_id=session_id,
            trigger=ReadingCompanionEpisodeTrigger.MANUAL_READING,
            start_message_id="user-1",
            book_id="book-1",
            chapter_id="chapter-2",
            unit_id="unit-2",
            selected_text="Mr. Gray",
        ),
        conversation=messages,
        tool_call_count=1,
    )


def _client():
    coordinator = FakeCoordinator()
    app = FastAPI()
    app.include_router(create_reading_companion_router(coordinator))
    return TestClient(app), coordinator


def test_create_session_trims_input_and_hides_internal_tool_messages():
    client, coordinator = _client()

    response = client.post(
        "/api/reading-companion/sessions",
        json={
            "session_id": " session-1 ",
            "current_unit_id": " unit-2 ",
            "message": " 他以前出现过吗？ ",
            "selected_text": " Mr. Gray ",
        },
    )

    assert response.status_code == 201
    assert coordinator.started == {
        "session_id": "session-1",
        "current_unit_id": "unit-2",
        "user_message": "他以前出现过吗？",
        "selected_text": "Mr. Gray",
    }
    assert response.json() == {
        "session_id": "session-1",
        "episode_id": "session-1-episode",
        "trigger": "manual_reading",
        "book_id": "book-1",
        "chapter_id": "chapter-2",
        "unit_id": "unit-2",
        "selected_text": "Mr. Gray",
        "messages": [
            {"role": "user", "content": "他以前出现过吗？"},
            {"role": "assistant", "content": "回答"},
        ],
        "error_code": "",
    }


def test_continue_retry_and_get_session():
    client, coordinator = _client()
    coordinator.states["session-1"] = _public_state()

    continued = client.post(
        "/api/reading-companion/sessions/session-1/messages",
        json={"message": " 第一次在哪里？ "},
    )
    retried = client.post(
        "/api/reading-companion/sessions/session-1/retry"
    )
    restored = client.get(
        "/api/reading-companion/sessions/session-1"
    )

    assert continued.status_code == 200
    assert coordinator.resumed == ("session-1", "第一次在哪里？")
    assert continued.json()["messages"][-1]["content"] == "继续回答"
    assert retried.status_code == 200
    assert coordinator.retried == "session-1"
    assert restored.status_code == 200
    assert restored.json()["messages"][-1]["content"] == "重试成功"


def test_http_maps_missing_conflict_stale_and_invalid_turn_errors():
    client, coordinator = _client()

    missing = client.get("/api/reading-companion/sessions/missing")
    coordinator.start_error = ReadingCompanionSessionConflictError(
        "already exists"
    )
    conflict = client.post(
        "/api/reading-companion/sessions",
        json={
            "current_unit_id": "unit-2",
            "message": "问题",
        },
    )
    coordinator.start_error = ManualReadingCompanionError(
        "no_active_reading",
        "unknown unit",
    )
    unknown_unit = client.post(
        "/api/reading-companion/sessions",
        json={
            "current_unit_id": "missing",
            "message": "问题",
        },
    )
    coordinator.resume_error = ReadingCompanionSessionNotFoundError(
        "missing"
    )
    missing_resume = client.post(
        "/api/reading-companion/sessions/missing/messages",
        json={"message": "问题"},
    )
    coordinator.retry_error = ReadingCompanionStateError("not retryable")
    invalid_retry = client.post(
        "/api/reading-companion/sessions/session-1/retry"
    )

    assert missing.status_code == 404
    assert conflict.status_code == 409
    assert unknown_unit.status_code == 404
    assert missing_resume.status_code == 404
    assert invalid_retry.status_code == 409


def test_http_rejects_whitespace_only_unit_and_messages():
    client, coordinator = _client()

    blank_unit = client.post(
        "/api/reading-companion/sessions",
        json={"current_unit_id": "  ", "message": "问题"},
    )
    blank_start_message = client.post(
        "/api/reading-companion/sessions",
        json={"current_unit_id": "unit-2", "message": "  "},
    )
    blank_resume_message = client.post(
        "/api/reading-companion/sessions/session-1/messages",
        json={"message": "  "},
    )

    assert blank_unit.status_code == 400
    assert blank_start_message.status_code == 400
    assert blank_resume_message.status_code == 400
    assert coordinator.started is None
