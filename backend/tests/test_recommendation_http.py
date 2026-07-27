"""HTTP contract tests for recommendation conversations."""

from dataclasses import replace
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from superhp_agent.contracts import (
    BookCandidate,
    BookDifficulty,
    BookEntryKind,
    BookRecommendationHandoff,
    BookSnapshot,
    LLMToolCall,
    OperationalReadingBand,
    ReadingDifficultyEvidence,
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
        self.retried = None
        self.start_reply = None
        self.resume_reply = None
        self.handoff_reply = None
        self.retry_reply = None

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

    async def retry(self, session_id):
        self.retried = session_id
        assert self.retry_reply is not None
        self.sessions[session_id] = self.retry_reply.session
        return self.retry_reply

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


class FakeDifficultyHandoffBuilder:
    def __init__(self):
        self.calls = []

    async def build(
        self,
        book_id,
        *,
        evidence,
        preserve_genre_by_default=True,
    ):
        self.calls.append(
            (
                book_id,
                evidence,
                preserve_genre_by_default,
            )
        )
        current_book = BookSnapshot(
            book_id=book_id,
            title="Harry Potter and the Philosopher's Stone",
            author="J. K. Rowling",
            difficulty=BookDifficulty(880, 940),
            genres=("fantasy",),
            progress=0.25,
        )
        target_band = OperationalReadingBand(680, 840)
        return RecommendationRequest(
            origin=RecommendationOrigin.DIFFICULTY_ALERT,
            preferred_genres=(
                current_book.genres if preserve_genre_by_default else ()
            ),
            operational_band=target_band,
            reference_books=(current_book,),
            handoff=BookRecommendationHandoff(
                current_book=current_book,
                evidence=evidence,
                target_band=target_band,
                preserve_genre_by_default=preserve_genre_by_default,
            ),
        )


def make_client(difficulty_prompt_coordinator=None):
    runner = FakeRecommendationRunner()
    catalog = FakeCatalog()
    handoff_builder = FakeDifficultyHandoffBuilder()
    coordinator = (
        difficulty_prompt_coordinator
        or FakeDifficultyPromptCoordinator()
    )
    app = FastAPI()
    app.include_router(
        create_recommendation_router(
            runner,
            catalog,
            handoff_builder,
            coordinator,
        )
    )
    return TestClient(app), runner


class FakeDifficultyPromptCoordinator:
    def __init__(self):
        self.required_book_ids = []
        self.changed = []
        self.evidence = ReadingDifficultyEvidence(
            observed_word_count=7200,
            observed_chapter_count=3,
            lookup_density=12.1,
            annotated_lookup_density=3.2,
            annotation_target=20,
        )

    def require_pending(self, book_id):
        self.required_book_ids.append(book_id)
        return SimpleNamespace(evidence=self.evidence)

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
        selected_catalog_id="cam-jansen",
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
            "selected_catalog_id": "",
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
    assert response.json()["selected_catalog_id"] == "cam-jansen"


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
            "book_id": "hp01",
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


def test_retry_session_continues_without_adding_a_user_message():
    client, runner = make_client()
    pending = replace(
        question_session(),
        phase=RecommendationAgentPhase.COLLECTING_PREFERENCES,
        conversation=(),
        error_code="model_error",
    )
    recovered = replace(
        question_session(),
        error_code="",
    )
    runner.sessions["session-1"] = pending
    runner.retry_reply = RecommendationAgentReply(
        session=recovered,
        message="你喜欢哪类故事？",
    )

    response = client.post(
        "/api/recommendations/sessions/session-1/retry"
    )

    assert response.status_code == 200
    assert runner.retried == "session-1"
    assert response.json()["phase"] == "awaiting_user"
    assert response.json()["error_code"] == ""
    assert response.json()["messages"] == [
        {"role": "assistant", "content": "你喜欢哪类故事？"}
    ]


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
