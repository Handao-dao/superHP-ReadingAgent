"""Tests for the bounded book-recommendation Agent loop."""

import json

import pytest

from superhp_agent.agent_tools import ToolRegistry
from superhp_agent.agents import (
    BookRecommendationAgent,
    RecommendationContextBuilder,
)
from superhp_agent.agents.book_recommendation import (
    RecommendationAgentStateError,
)
from superhp_agent.contracts import (
    LLMResponse,
    RecommendationAgentMessageRole,
    RecommendationAgentPhase,
    RecommendationOrigin,
    RecommendationRequest,
)


def ask(message: str) -> str:
    return json.dumps(
        {"action": "ask_user", "message": message},
        ensure_ascii=False,
    )


def search(
    *,
    lexile_min: int = 400,
    lexile_max: int = 700,
    genres: tuple[str, ...] = ("mystery",),
    limit: int = 5,
    tool_name: str = "search_local_book_catalog",
) -> str:
    return json.dumps(
        {
            "action": "call_tool",
            "tool_name": tool_name,
            "arguments": {
                "lexile_min": lexile_min,
                "lexile_max": lexile_max,
                "genres": list(genres),
                "limit": limit,
            },
        }
    )


def finalize(*catalog_ids: str, message: str = "推荐完成。") -> str:
    return json.dumps(
        {
            "action": "finalize",
            "message": message,
            "recommended_catalog_ids": list(catalog_ids),
        },
        ensure_ascii=False,
    )


class ScriptedProvider:
    """Return pre-written model text while recording constructed messages."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    async def chat_with_retry(self, messages, *, on_retry_wait=None):
        self.calls.append(messages)
        if not self.responses:
            raise AssertionError("scripted provider ran out of responses")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, LLMResponse):
            return response
        return LLMResponse(content=response)


class RecordingCatalogTool:
    """Return JSON-ready candidates and record the exact Registry call."""

    name = "search_local_book_catalog"
    description = "Search the local book catalog."
    input_schema = {"type": "object"}

    def __init__(self, candidate_ids=("cam-jansen", "nate-the-great")):
        self.candidate_ids = candidate_ids
        self.calls = []

    async def run(self, **arguments):
        self.calls.append(arguments)
        return {
            "tool": self.name,
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


def make_agent(
    provider,
    tool=None,
    *,
    extra_tools=(),
    **kwargs,
):
    tool = tool or RecordingCatalogTool()
    registry = ToolRegistry((tool, *extra_tools))
    return (
        BookRecommendationAgent(
            provider,
            RecommendationContextBuilder(),
            registry,
            **kwargs,
        ),
        tool,
    )


@pytest.mark.asyncio
async def test_agent_pauses_for_user_then_searches_and_finalizes():
    provider = ScriptedProvider(
        ask("你喜欢哪类故事？"),
        search(),
        finalize(
            "cam-jansen",
            "nate-the-great",
            message="这两套侦探故事适合作为起点。",
        ),
    )
    agent, tool = make_agent(provider)
    session = agent.start(onboarding_request(), session_id="session-1")

    question = await agent.run(session)

    assert question.session.phase is RecommendationAgentPhase.AWAITING_USER
    assert question.message == "你喜欢哪类故事？"
    assert question.session.tool_call_count == 0
    assert '"remaining_tool_calls": 3' in provider.calls[0][-1]["content"]

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
            "genres": ["mystery"],
            "limit": 5,
        }
    ]


@pytest.mark.asyncio
async def test_agent_accepts_json_inside_a_markdown_fence():
    provider = ScriptedProvider(
        "```json\n" + ask("你想读什么类型？") + "\n```"
    )
    agent, _ = make_agent(provider)

    reply = await agent.run(agent.start(onboarding_request(), session_id="session"))

    assert reply.session.phase is RecommendationAgentPhase.AWAITING_USER
    assert reply.message == "你想读什么类型？"


@pytest.mark.asyncio
async def test_agent_rejects_unobserved_final_ids_and_recovers():
    provider = ScriptedProvider(
        finalize("invented-book"),
        search(),
        finalize("cam-jansen"),
    )
    agent, _ = make_agent(
        provider,
        RecordingCatalogTool(("cam-jansen",)),
    )

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
    provider = ScriptedProvider(
        search(),
        search(genres=("adventure",)),
        ask("当前严格条件没有合适结果，要放宽难度吗？"),
    )
    agent, tool = make_agent(
        provider,
        RecordingCatalogTool(()),
        max_tool_calls=1,
    )

    reply = await agent.run(agent.start(onboarding_request(), session_id="session"))

    assert reply.session.phase is RecommendationAgentPhase.AWAITING_USER
    assert reply.session.tool_call_count == 1
    assert len(tool.calls) == 1
    assert '"remaining_tool_calls": 0' in provider.calls[-1][-1]["content"]
    last_tool_payload = json.loads(reply.session.conversation[-2].content)
    assert last_tool_payload["error"] == "tool_call_limit_reached"


@pytest.mark.asyncio
async def test_agent_returns_invalid_tool_arguments_to_model():
    provider = ScriptedProvider(
        search(limit=20),
        ask("我会缩小候选范围，你更偏好单本还是系列？"),
    )
    tool = RecordingCatalogTool()

    async def reject_large_limit(**arguments):
        raise ValueError("limit must not exceed 10 candidates")

    tool.run = reject_large_limit
    agent, _ = make_agent(provider, tool)

    reply = await agent.run(agent.start(onboarding_request(), session_id="session"))

    assert reply.session.phase is RecommendationAgentPhase.AWAITING_USER
    payload = json.loads(reply.session.conversation[0].content)
    assert payload["error"] == "invalid_tool_arguments"
    assert payload["tool"] == "search_local_book_catalog"


@pytest.mark.asyncio
async def test_agent_stops_after_decision_limit():
    provider = ScriptedProvider(search(), search(genres=("adventure",)))
    agent, _ = make_agent(
        provider,
        RecordingCatalogTool(()),
        max_decisions_per_run=2,
    )

    reply = await agent.run(agent.start(onboarding_request(), session_id="session"))

    assert reply.session.phase is RecommendationAgentPhase.FAILED
    assert reply.error_code == "decision_limit_reached"
    assert reply.session.tool_call_count == 2


@pytest.mark.asyncio
async def test_agent_normalizes_provider_failure_into_failed_reply():
    provider = ScriptedProvider(
        LLMResponse(content="provider unavailable", finish_reason="error")
    )
    agent, _ = make_agent(provider)

    reply = await agent.run(agent.start(onboarding_request(), session_id="session"))

    assert reply.session.phase is RecommendationAgentPhase.FAILED
    assert reply.error_code == "model_error"
    assert "稍后重试" in reply.message


@pytest.mark.asyncio
async def test_agent_rejects_invalid_model_decision():
    provider = ScriptedProvider('{"action":"search_catalog"}')
    agent, _ = make_agent(provider)

    reply = await agent.run(agent.start(onboarding_request(), session_id="session"))

    assert reply.session.phase is RecommendationAgentPhase.FAILED
    assert reply.error_code == "invalid_model_decision"


@pytest.mark.asyncio
async def test_awaiting_user_session_requires_message_and_completed_cannot_resume():
    provider = ScriptedProvider(
        ask("请补充偏好。"),
        search(),
        finalize("cam-jansen"),
    )
    agent, _ = make_agent(
        provider,
        RecordingCatalogTool(("cam-jansen",)),
    )
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
