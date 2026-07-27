"""HTTP contract tests for recommendation conversations."""

from dataclasses import replace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from superhp_agent.contracts import (
    BookCandidate,
    BookDifficulty,
    BookEntryKind,
    LLMToolCall,
    RecommendationAgentMessage,
    RecommendationAgentMessageRole,
    RecommendationAgentPhase,
    RecommendationAgentReply,
    RecommendationAgentSession,
    RecommendationOrigin,
    RecommendationRequest,
)
from superhp_agent.transport.recommendation_http import (
    create_recommendation_router,
)


class FakeRecommendationRunner:
    def __init__(self):
        self.sessions = {}
        self.started_request = None
        self.resumed = None
        self.handed_off = None
        self.start_reply = None
        self.resume_reply = None
        self.handoff_reply = None

    async def start(self, request):
        self.started_request = request
        assert self.start_reply is not None
        self.sessions[self.start_reply.session.session_id] = self.start_reply.session
        return self.start_reply

    async def resume(self, session_id, *, user_message):
        self.resumed = (session_id, user_message)
        assert self.resume_reply is not None
        self.sessions[session_id] = self.resume_reply.session
        return self.resume_reply

    async def handoff(self, request, *, session_id=None, user_message):
        self.handed_off = (request, session_id, user_message)
        assert self.handoff_reply is not None
        self.sessions[self.handoff_reply.session.session_id] = (
            self.handoff_reply.session
        )
        return self.handoff_reply

    def load(self, session_id):
        return self.sessions.get(session_id)


class FakeCatalog:
    def __init__(self):
        self.candidates = {
            "cam-jansen": BookCandidate(
                catalog_id="cam-jansen",
                title_en="Cam Jansen",
                title_zh="校园小侦探",
                author="David A. Adler",
                difficulty=BookDifficulty(420, 600),
                entry_kind=BookEntryKind.SERIES,
                genres=("mystery", "school_life"),
            )
        }

    async def find_by_id(self, catalog_id):
        return self.candidates.get(catalog_id)

    async def search_books(self, query):
        raise AssertionError("HTTP projection must not search the catalog")


def make_client(difficulty_prompt_coordinator=None):
    runner = FakeRecommendationRunner()
    catalog = FakeCatalog()
    app = FastAPI()
    app.include_router(
        create_recommendation_router(
            runner,
            catalog,
            difficulty_prompt_coordinator,
        )
    )
    return TestClient(app), runner


class FakeDifficultyPromptCoordinator:
    def __init__(self):
        self.required_book_ids = []
        self.changed = []

    def require_pending(self, book_id):
        self.required_book_ids.append(book_id)

    def choose_change_book(
        self,
        book_id,
        *,
        recommendation_session_id,
    ):
        self.changed.append((book_id, recommendation_session_id))


def question_session() -> RecommendationAgentSession:
    return RecommendationAgentSession(
        session_id="session-1",
        request=RecommendationRequest(origin=RecommendationOrigin.ONBOARDING),
        phase=RecommendationAgentPhase.AWAITING_USER,
        conversation=(
            RecommendationAgentMessage(
                role=RecommendationAgentMessageRole.ASSISTANT,
                content="你喜欢哪类故事？",
            ),
        ),
    )


def completed_session() -> RecommendationAgentSession:
    tool_call = LLMToolCall(
        id="present-1",
        name="present_book_recommendations",
        arguments={
            "catalog_ids": ["cam-jansen"],
            "message": "Cam Jansen 比较适合作为新的起点。",
        },
    )
    return RecommendationAgentSession(
        session_id="session-1",
        request=RecommendationRequest(origin=RecommendationOrigin.ONBOARDING),
        phase=RecommendationAgentPhase.COMPLETED,
        conversation=(
            RecommendationAgentMessage(
                role=RecommendationAgentMessageRole.ASSISTANT,
                content="你喜欢哪类故事？",
            ),
            RecommendationAgentMessage(
                role=RecommendationAgentMessageRole.USER,
                content="轻松的侦探故事。",
            ),
            RecommendationAgentMessage(
                role=RecommendationAgentMessageRole.ASSISTANT,
                tool_calls=(tool_call,),
            ),
            RecommendationAgentMessage(
                role=RecommendationAgentMessageRole.TOOL,
                content='{"ok":true}',
                tool_call_id="present-1",
                tool_name="present_book_recommendations",
            ),
            RecommendationAgentMessage(
                role=RecommendationAgentMessageRole.ASSISTANT,
                content="Cam Jansen 比较适合作为新的起点。",
            ),
        ),
        tool_call_count=1,
        observed_catalog_ids=("cam-jansen",),
        recommended_catalog_ids=("cam-jansen",),
    )


def test_create_session_returns_only_user_visible_messages():
    client, runner = make_client()
    session = question_session()
    runner.start_reply = RecommendationAgentReply(
        session=session,
        message="你喜欢哪类故事？",
    )

    response = client.post(
        "/api/recommendations/sessions",
        json={
            "preferred_genres": [" mystery ", "Mystery", ""],
            "excluded_traits": ["horror"],
            "user_notes": " 希望故事轻松一些。 ",
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "session_id": "session-1",
        "origin": "onboarding",
        "phase": "awaiting_user",
        "messages": [
            {"role": "assistant", "content": "你喜欢哪类故事？"},
        ],
        "recommended_books": [],
        "error_code": "",
    }
    assert runner.started_request.preferred_genres == ("mystery",)
    assert runner.started_request.excluded_traits == ("horror",)
    assert runner.started_request.user_notes == "希望故事轻松一些。"


def test_continue_session_returns_verified_cards_and_hides_tools():
    client, runner = make_client()
    runner.sessions["session-1"] = question_session()
    session = completed_session()
    runner.resume_reply = RecommendationAgentReply(
        session=session,
        message="Cam Jansen 比较适合作为新的起点。",
        recommended_catalog_ids=("cam-jansen",),
    )

    response = client.post(
        "/api/recommendations/sessions/session-1/messages",
        json={"message": " 轻松的侦探故事。 "},
    )

    assert response.status_code == 200
    body = response.json()
    assert runner.resumed == ("session-1", "轻松的侦探故事。")
    assert [message["role"] for message in body["messages"]] == [
        "assistant",
        "user",
        "assistant",
    ]
    assert body["recommended_books"] == [
        {
            "catalog_id": "cam-jansen",
            "title_en": "Cam Jansen",
            "title_zh": "校园小侦探",
            "author": "David A. Adler",
            "entry_kind": "series",
            "lexile_min": 420,
            "lexile_max": 600,
            "genres": ["mystery", "school_life"],
        }
    ]


def test_get_session_restores_completed_public_view():
    client, runner = make_client()
    runner.sessions["session-1"] = completed_session()

    response = client.get("/api/recommendations/sessions/session-1")

    assert response.status_code == 200
    assert response.json()["phase"] == "completed"
    assert response.json()["recommended_books"][0]["catalog_id"] == "cam-jansen"


def test_difficulty_handoff_reuses_transcript_and_passes_reading_evidence():
    coordinator = FakeDifficultyPromptCoordinator()
    client, runner = make_client(coordinator)
    session = replace(
        question_session(),
        request=RecommendationRequest(
            origin=RecommendationOrigin.DIFFICULTY_ALERT
        ),
    )
    runner.handoff_reply = RecommendationAgentReply(
        session=session,
        message="我先分析最近的阅读情况。",
    )

    response = client.post(
        "/api/recommendations/difficulty-handoffs",
        json={
            "session_id": "session-1",
            "current_book": {
                "book_id": "hp01",
                "title": "Harry Potter and the Philosopher's Stone",
                "genres": ["fantasy"],
            },
            "evidence": {
                "observed_word_count": 7200,
                "observed_chapter_count": 3,
                "lookup_density": 12.1,
                "annotated_lookup_density": 3.2,
                "annotation_target": 20,
            },
        },
    )

    assert response.status_code == 201
    assert response.json()["origin"] == "difficulty_alert"
    request, session_id, message = runner.handed_off
    assert session_id == "session-1"
    assert request.handoff.current_book.book_id == "hp01"
    assert request.handoff.evidence.lookup_density == 12.1
    assert request.preferred_genres == ("fantasy",)
    assert "最近 3 章" in message
    assert coordinator.required_book_ids == ["hp01"]
    assert coordinator.changed == [("hp01", "session-1")]


def test_get_session_restores_failed_error_code():
    client, runner = make_client()
    runner.sessions["failed"] = replace(
        question_session(),
        session_id="failed",
        phase=RecommendationAgentPhase.FAILED,
        error_code="model_error",
    )

    response = client.get("/api/recommendations/sessions/failed")

    assert response.status_code == 200
    assert response.json()["phase"] == "failed"
    assert response.json()["error_code"] == "model_error"


def test_api_rejects_missing_sessions_blank_messages_and_unready_handoffs():
    client, runner = make_client()

    missing = client.get("/api/recommendations/sessions/missing")
    blank = client.post(
        "/api/recommendations/sessions/missing/messages",
        json={"message": "   "},
    )
    handoff = client.post(
        "/api/recommendations/sessions",
        json={"origin": "difficulty_alert"},
    )

    assert missing.status_code == 404
    assert blank.status_code == 400
    assert handoff.status_code == 400
    assert runner.started_request is None
