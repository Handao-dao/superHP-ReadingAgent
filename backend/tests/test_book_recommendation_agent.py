"""Tests for the bounded book-recommendation Agent loop."""

import json

import pytest

from superhp_agent.agents import BookRecommendationAgent
from superhp_agent.agents.book_recommendation import (
    RecommendationAgentStateError,
)
from superhp_agent.contracts import (
    BookSearchQuery,
    RecommendationAgentDecision,
    RecommendationAgentDecisionKind,
    RecommendationAgentMessageRole,
    RecommendationAgentPhase,
    RecommendationOrigin,
    RecommendationRequest,
)


def ask(message: str) -> RecommendationAgentDecision:
    return RecommendationAgentDecision(
        kind=RecommendationAgentDecisionKind.ASK_USER,
        message=message,
    )


def search(
    *,
    lexile_min: int = 400,
    lexile_max: int = 700,
    genres: tuple[str, ...] = ("mystery",),
    limit: int = 5,
) -> RecommendationAgentDecision:
    return RecommendationAgentDecision(
        kind=RecommendationAgentDecisionKind.SEARCH_CATALOG,
        search_query=BookSearchQuery(
            lexile_min=lexile_min,
            lexile_max=lexile_max,
            categories=genres,
            limit=limit,
        ),
    )


def finalize(*catalog_ids: str, message: str = "推荐完成。"):
    return RecommendationAgentDecision(
        kind=RecommendationAgentDecisionKind.FINALIZE,
        message=message,
        recommended_catalog_ids=catalog_ids,
    )


class ScriptedModel:
    """Return pre-written decisions while recording each observation."""

    def __init__(self, *decisions):
        self.decisions = list(decisions)
        self.observations = []

    async def decide(self, observation):
        self.observations.append(observation)
        if not self.decisions:
            raise AssertionError("scripted model ran out of decisions")
        decision = self.decisions.pop(0)
        if isinstance(decision, Exception):
            raise decision
        return decision


class RecordingCatalogTool:
    """Return JSON-ready candidates and record the exact Agent call."""

    def __init__(self, candidate_ids=("cam-jansen", "nate-the-great")):
        self.candidate_ids = candidate_ids
        self.calls = []

    async def run(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "tool": "search_local_book_catalog",
            "match_mode": "strict",
            "found": bool(self.candidate_ids),
            "result_count": len(self.candidate_ids),
            "candidates": [
                {
                    "catalog_id": catalog_id,
                    "title_en": catalog_id.replace("-", " ").title(),
                }
                for catalog_id in self.candidate_ids
            ],
        }


def onboarding_request() -> RecommendationRequest:
    return RecommendationRequest(origin=RecommendationOrigin.ONBOARDING)


@pytest.mark.asyncio
async def test_agent_pauses_for_user_then_searches_and_finalizes():
    model = ScriptedModel(
        ask("你喜欢哪类故事？"),
        search(),
        finalize(
            "cam-jansen",
            "nate-the-great",
            message="这两套侦探故事适合作为起点。",
        ),
    )
    tool = RecordingCatalogTool()
    agent = BookRecommendationAgent(model, tool)
    session = agent.start(onboarding_request(), session_id="session-1")

    question = await agent.run(session)

    assert question.session.phase is RecommendationAgentPhase.AWAITING_USER
    assert question.message == "你喜欢哪类故事？"
    assert question.session.tool_call_count == 0
    assert model.observations[0].remaining_tool_calls == 3

    answer = await agent.run(
        question.session,
        user_message="我喜欢轻松的侦探故事。",
    )

    assert answer.session.phase is RecommendationAgentPhase.COMPLETED
    assert answer.recommended_catalog_ids == (
        "cam-jansen",
        "nate-the-great",
    )
    assert answer.session.observed_catalog_ids == (
        "cam-jansen",
        "nate-the-great",
    )
    assert answer.session.tool_call_count == 1
    assert [message.role for message in answer.session.conversation] == [
        RecommendationAgentMessageRole.ASSISTANT,
        RecommendationAgentMessageRole.USER,
        RecommendationAgentMessageRole.TOOL,
        RecommendationAgentMessageRole.ASSISTANT,
    ]
    assert tool.calls == [
        {
            "lexile_min": 400,
            "lexile_max": 700,
            "genres": ("mystery",),
            "entry_kinds": (),
            "excluded_ids": (),
            "limit": 5,
        }
    ]


@pytest.mark.asyncio
async def test_agent_rejects_unobserved_final_ids_and_lets_model_recover():
    model = ScriptedModel(
        finalize("invented-book"),
        search(),
        finalize("cam-jansen"),
    )
    agent = BookRecommendationAgent(model, RecordingCatalogTool(("cam-jansen",)))

    reply = await agent.run(agent.start(onboarding_request(), session_id="session"))

    assert reply.session.phase is RecommendationAgentPhase.COMPLETED
    assert reply.recommended_catalog_ids == ("cam-jansen",)
    first_tool_message = reply.session.conversation[0]
    assert first_tool_message.role is RecommendationAgentMessageRole.TOOL
    assert json.loads(first_tool_message.content) == {
        "catalog_ids": ["invented-book"],
        "error": "unobserved_recommendation_ids",
        "ok": False,
    }


@pytest.mark.asyncio
async def test_agent_enforces_tool_budget_without_executing_extra_call():
    model = ScriptedModel(
        search(),
        search(genres=("adventure",)),
        ask("当前严格条件没有合适结果，要放宽难度吗？"),
    )
    tool = RecordingCatalogTool(())
    agent = BookRecommendationAgent(model, tool, max_tool_calls=1)

    reply = await agent.run(agent.start(onboarding_request(), session_id="session"))

    assert reply.session.phase is RecommendationAgentPhase.AWAITING_USER
    assert reply.session.tool_call_count == 1
    assert len(tool.calls) == 1
    assert model.observations[-1].remaining_tool_calls == 0
    last_tool_payload = json.loads(reply.session.conversation[-2].content)
    assert last_tool_payload["error"] == "tool_call_limit_reached"


@pytest.mark.asyncio
async def test_agent_rejects_oversized_search_before_tool_execution():
    model = ScriptedModel(
        search(limit=20),
        ask("我会缩小候选范围，你更偏好单本还是系列？"),
    )
    tool = RecordingCatalogTool()
    agent = BookRecommendationAgent(
        model,
        tool,
        max_candidates_per_search=10,
    )

    reply = await agent.run(agent.start(onboarding_request(), session_id="session"))

    assert reply.session.phase is RecommendationAgentPhase.AWAITING_USER
    assert reply.session.tool_call_count == 1
    assert tool.calls == []
    payload = json.loads(reply.session.conversation[0].content)
    assert payload == {
        "error": "candidate_limit_too_large",
        "maximum": 10,
        "ok": False,
    }


@pytest.mark.asyncio
async def test_agent_stops_after_decision_limit():
    model = ScriptedModel(search(), search(genres=("adventure",)))
    agent = BookRecommendationAgent(
        model,
        RecordingCatalogTool(()),
        max_decisions_per_run=2,
    )

    reply = await agent.run(agent.start(onboarding_request(), session_id="session"))

    assert reply.session.phase is RecommendationAgentPhase.FAILED
    assert reply.error_code == "decision_limit_reached"
    assert reply.session.tool_call_count == 2


@pytest.mark.asyncio
async def test_agent_normalizes_model_failure_into_failed_reply():
    model = ScriptedModel(RuntimeError("provider unavailable"))
    agent = BookRecommendationAgent(model, RecordingCatalogTool())

    reply = await agent.run(agent.start(onboarding_request(), session_id="session"))

    assert reply.session.phase is RecommendationAgentPhase.FAILED
    assert reply.error_code == "model_error"
    assert "稍后重试" in reply.message


@pytest.mark.asyncio
async def test_agent_rejects_non_contract_model_decision():
    model = ScriptedModel({"action": "search_catalog"})
    agent = BookRecommendationAgent(model, RecordingCatalogTool())

    reply = await agent.run(agent.start(onboarding_request(), session_id="session"))

    assert reply.session.phase is RecommendationAgentPhase.FAILED
    assert reply.error_code == "invalid_model_decision"


@pytest.mark.asyncio
async def test_awaiting_user_session_requires_message_and_completed_cannot_resume():
    model = ScriptedModel(ask("请补充偏好。"), search(), finalize("cam-jansen"))
    agent = BookRecommendationAgent(model, RecordingCatalogTool(("cam-jansen",)))
    question = await agent.run(
        agent.start(onboarding_request(), session_id="session")
    )

    with pytest.raises(
        RecommendationAgentStateError,
        match="requires a user message",
    ):
        await agent.run(question.session)

    completed = await agent.run(question.session, user_message="侦探故事")
    with pytest.raises(RecommendationAgentStateError, match="cannot continue"):
        await agent.run(completed.session, user_message="再推荐一次")
