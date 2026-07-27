"""Tests for the native-message book-recommendation Agent loop."""

import json

import pytest

from superhp_agent.agent_tools import (
    PresentBookRecommendationsTool,
    ToolRegistry,
)
from superhp_agent.agents import (
    BookRecommendationAgent,
    RecommendationContextBuilder,
)
from superhp_agent.agents.book_recommendation import (
    RecommendationAgentStateError,
)
from superhp_agent.contracts import (
    LLMResponse,
    LLMToolCall,
    RecommendationAgentMessageRole,
    RecommendationAgentPhase,
    RecommendationOrigin,
    RecommendationRequest,
)


def call(
    name: str,
    arguments: dict[str, object],
    *,
    call_id: str,
    arguments_error: str = "",
) -> LLMResponse:
    return LLMResponse(
        content=None,
        finish_reason="tool_calls",
        tool_calls=(
            LLMToolCall(
                id=call_id,
                name=name,
                arguments=arguments,
                arguments_error=arguments_error,
            ),
        ),
    )


def search(
    *,
    call_id: str = "search-1",
    genres: tuple[str, ...] = ("mystery",),
) -> LLMResponse:
    return call(
        "search_local_book_catalog",
        {
            "lexile_min": 400,
            "lexile_max": 700,
            "genres": list(genres),
            "limit": 5,
        },
        call_id=call_id,
    )


def present(
    *catalog_ids: str,
    call_id: str = "present-1",
    message: str = "推荐完成。",
) -> LLMResponse:
    return call(
        "present_book_recommendations",
        {
            "catalog_ids": list(catalog_ids),
            "message": message,
        },
        call_id=call_id,
    )


class ScriptedProvider:
    """Return pre-written responses and record messages plus tool schemas."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    async def chat_with_retry(
        self,
        messages,
        *,
        tools=None,
        on_retry_wait=None,
    ):
        self.calls.append({"messages": messages, "tools": tools})
        if not self.responses:
            raise AssertionError("scripted provider ran out of responses")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class RecordingCatalogTool:
    """Return JSON-ready candidates and record exact Registry calls."""

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
            "found": bool(self.candidate_ids),
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


def make_agent(provider, catalog_tool=None, **kwargs):
    catalog_tool = catalog_tool or RecordingCatalogTool()
    registry = ToolRegistry(
        (
            catalog_tool,
            PresentBookRecommendationsTool(),
        )
    )
    return (
        BookRecommendationAgent(
            provider,
            RecommendationContextBuilder(),
            registry,
            **kwargs,
        ),
        catalog_tool,
    )


@pytest.mark.asyncio
async def test_plain_assistant_text_pauses_for_user():
    provider = ScriptedProvider(LLMResponse(content="你喜欢哪类故事？"))
    agent, _ = make_agent(provider)

    reply = await agent.run(
        agent.start(onboarding_request(), session_id="session")
    )

    assert reply.session.phase is RecommendationAgentPhase.AWAITING_USER
    assert reply.message == "你喜欢哪类故事？"
    assert reply.session.conversation[0].role is (
        RecommendationAgentMessageRole.ASSISTANT
    )
    tool_names = [
        tool["function"]["name"]
        for tool in provider.calls[0]["tools"]
    ]
    assert tool_names == [
        "search_local_book_catalog",
        "present_book_recommendations",
    ]


@pytest.mark.asyncio
async def test_agent_searches_then_finishes_with_verified_candidates():
    provider = ScriptedProvider(
        LLMResponse(content="你喜欢哪类故事？"),
        search(),
        present(
            "cam-jansen",
            "nate-the-great",
            message="这两套侦探故事适合作为起点。",
        ),
    )
    agent, tool = make_agent(provider)
    question = await agent.run(
        agent.start(onboarding_request(), session_id="session-1")
    )

    answer = await agent.run(
        question.session,
        user_message="我喜欢轻松的侦探故事。",
    )

    assert answer.session.phase is RecommendationAgentPhase.COMPLETED
    assert answer.message == "这两套侦探故事适合作为起点。"
    assert answer.recommended_catalog_ids == (
        "cam-jansen",
        "nate-the-great",
    )
    assert answer.session.recommended_catalog_ids == (
        "cam-jansen",
        "nate-the-great",
    )
    assert answer.session.observed_catalog_ids == (
        "cam-jansen",
        "nate-the-great",
    )
    assert answer.session.tool_call_count == 2
    assert [message.role for message in answer.session.conversation] == [
        RecommendationAgentMessageRole.ASSISTANT,
        RecommendationAgentMessageRole.USER,
        RecommendationAgentMessageRole.ASSISTANT,
        RecommendationAgentMessageRole.TOOL,
        RecommendationAgentMessageRole.ASSISTANT,
        RecommendationAgentMessageRole.TOOL,
        RecommendationAgentMessageRole.ASSISTANT,
    ]
    assert answer.session.conversation[2].tool_calls[0].id == "search-1"
    assert answer.session.conversation[3].tool_call_id == "search-1"
    assert answer.session.conversation[-1].content == (
        "这两套侦探故事适合作为起点。"
    )
    assert tool.calls[0]["genres"] == ["mystery"]

    final_provider_messages = provider.calls[-1]["messages"]
    assert final_provider_messages[-2]["role"] == "assistant"
    assert final_provider_messages[-2]["tool_calls"][0]["id"] == "search-1"
    assert final_provider_messages[-1] == {
        "role": "tool",
        "tool_call_id": "search-1",
        "content": answer.session.conversation[3].content,
    }


@pytest.mark.asyncio
async def test_unobserved_terminal_ids_return_tool_error_and_model_recovers():
    provider = ScriptedProvider(
        present("invented-book", call_id="present-bad"),
        search(call_id="search-2"),
        present("cam-jansen", call_id="present-good"),
    )
    agent, _ = make_agent(
        provider,
        RecordingCatalogTool(("cam-jansen",)),
    )

    reply = await agent.run(
        agent.start(onboarding_request(), session_id="session")
    )

    assert reply.session.phase is RecommendationAgentPhase.COMPLETED
    assert reply.recommended_catalog_ids == ("cam-jansen",)
    first_tool_result = reply.session.conversation[1]
    assert first_tool_result.is_error is True
    assert json.loads(first_tool_result.content)["error"] == (
        "unobserved_recommendation_ids"
    )


@pytest.mark.asyncio
async def test_search_and_present_in_same_assistant_turn_cannot_use_new_ids():
    response = LLMResponse(
        content=None,
        finish_reason="tool_calls",
        tool_calls=(
            search().tool_calls[0],
            present("cam-jansen").tool_calls[0],
        ),
    )
    provider = ScriptedProvider(
        response,
        present("cam-jansen", call_id="present-after-observation"),
    )
    agent, _ = make_agent(
        provider,
        RecordingCatalogTool(("cam-jansen",)),
    )

    reply = await agent.run(
        agent.start(onboarding_request(), session_id="session")
    )

    assert reply.session.phase is RecommendationAgentPhase.COMPLETED
    terminal_error = reply.session.conversation[2]
    assert terminal_error.is_error is True
    assert json.loads(terminal_error.content)["error"] == (
        "unobserved_recommendation_ids"
    )


@pytest.mark.asyncio
async def test_tool_argument_parse_error_is_returned_to_model():
    invalid_call = call(
        "search_local_book_catalog",
        {},
        call_id="invalid-args",
        arguments_error="invalid tool arguments JSON",
    )
    provider = ScriptedProvider(
        invalid_call,
        LLMResponse(content="请告诉我你喜欢的题材。"),
    )
    agent, tool = make_agent(provider)

    reply = await agent.run(
        agent.start(onboarding_request(), session_id="session")
    )

    assert reply.session.phase is RecommendationAgentPhase.AWAITING_USER
    assert tool.calls == []
    payload = json.loads(reply.session.conversation[1].content)
    assert payload["error"] == "invalid_tool_arguments"


@pytest.mark.asyncio
async def test_truncated_tool_call_is_not_executed():
    truncated = search()
    truncated.finish_reason = "length"
    provider = ScriptedProvider(
        truncated,
        LLMResponse(content="请再告诉我一个偏好。"),
    )
    agent, tool = make_agent(provider)

    reply = await agent.run(
        agent.start(onboarding_request(), session_id="session")
    )

    assert reply.session.phase is RecommendationAgentPhase.AWAITING_USER
    assert tool.calls == []
    payload = json.loads(reply.session.conversation[1].content)
    assert payload["error"] == "truncated_tool_call"


@pytest.mark.asyncio
async def test_agent_enforces_tool_budget_and_returns_error_to_model():
    provider = ScriptedProvider(
        search(),
        search(call_id="search-over-budget", genres=("adventure",)),
        LLMResponse(content="当前结果不足，要放宽难度吗？"),
    )
    agent, tool = make_agent(
        provider,
        RecordingCatalogTool(()),
        max_tool_calls=1,
    )

    reply = await agent.run(
        agent.start(onboarding_request(), session_id="session")
    )

    assert reply.session.phase is RecommendationAgentPhase.AWAITING_USER
    assert len(tool.calls) == 1
    assert reply.session.tool_call_count == 1
    budget_error = json.loads(reply.session.conversation[-2].content)
    assert budget_error["error"] == "tool_call_limit_reached"


@pytest.mark.asyncio
async def test_agent_stops_after_model_turn_limit():
    provider = ScriptedProvider(search(), search(call_id="search-2"))
    agent, _ = make_agent(
        provider,
        RecordingCatalogTool(()),
        max_model_turns_per_run=2,
    )

    reply = await agent.run(
        agent.start(onboarding_request(), session_id="session")
    )

    assert reply.session.phase is RecommendationAgentPhase.FAILED
    assert reply.error_code == "turn_limit_reached"


@pytest.mark.asyncio
async def test_agent_normalizes_provider_and_empty_response_failures():
    provider = ScriptedProvider(
        LLMResponse(content="provider unavailable", finish_reason="error")
    )
    agent, _ = make_agent(provider)

    failed = await agent.run(
        agent.start(onboarding_request(), session_id="provider-error")
    )

    assert failed.error_code == "model_error"
    assert failed.session.error_code == "model_error"

    empty_provider = ScriptedProvider(LLMResponse(content=None))
    empty_agent, _ = make_agent(empty_provider)
    empty = await empty_agent.run(
        empty_agent.start(onboarding_request(), session_id="empty")
    )
    assert empty.error_code == "invalid_model_response"


@pytest.mark.asyncio
async def test_awaiting_user_requires_message_and_completed_cannot_resume():
    provider = ScriptedProvider(
        LLMResponse(content="请补充偏好。"),
        search(),
        present("cam-jansen"),
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
