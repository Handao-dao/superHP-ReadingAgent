"""Tests for persistence around the recommendation Agent Loop."""

from dataclasses import replace

import pytest

from superhp_agent.agent_tools import ToolRegistry
from superhp_agent.agents import (
    BookRecommendationAgent,
    RecommendationContextBuilder,
)
from superhp_agent.application import (
    RecommendationAgentRunner,
    RecommendationSessionNotFoundError,
)
from superhp_agent.contracts import (
    LLMResponse,
    RecommendationAgentMessageRole,
    RecommendationAgentPhase,
    RecommendationOrigin,
    RecommendationRequest,
)


class InMemorySessionRepository:
    """Small Repository fake that also records durability boundaries."""

    def __init__(self):
        self.sessions = {}
        self.saved = []

    def save(self, session):
        self.sessions[session.session_id] = session
        self.saved.append(session)

    def load(self, session_id):
        return self.sessions.get(session_id)

    def delete(self, session_id):
        return self.sessions.pop(session_id, None) is not None


class ScriptedProvider:
    def __init__(self, *responses):
        self.responses = list(responses)

    async def chat_with_retry(
        self,
        messages,
        *,
        tools=None,
        on_retry_wait=None,
    ):
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def make_runner(*responses):
    repository = InMemorySessionRepository()
    created_agents = []

    def agent_factory():
        agent = BookRecommendationAgent(
            ScriptedProvider(*responses),
            RecommendationContextBuilder(),
            ToolRegistry(
                (
                    _UnusedTool("search_local_book_catalog"),
                    _UnusedTool("present_book_recommendations"),
                    _UnusedTool("select_recommended_book"),
                )
            ),
        )
        created_agents.append(agent)
        return agent

    return (
        RecommendationAgentRunner(agent_factory, repository),
        repository,
        created_agents,
    )


class _UnusedTool:
    description = "Unused test tool."
    input_schema = {"type": "object"}

    def __init__(self, name):
        self.name = name

    async def run(self, **arguments):
        raise AssertionError("this test does not call tools")


@pytest.mark.asyncio
async def test_runner_restores_the_same_conversation_before_resuming():
    runner, repository, created_agents = make_runner(
        LLMResponse(content="你喜欢哪类故事？"),
        LLMResponse(content="更喜欢轻松还是有挑战？"),
    )
    request = RecommendationRequest(origin=RecommendationOrigin.ONBOARDING)

    first = await runner.start(request, session_id="session-1")
    resumed = await runner.resume(
        "session-1",
        user_message="我喜欢侦探故事。",
    )

    assert first.session.phase is RecommendationAgentPhase.AWAITING_USER
    assert resumed.session.phase is RecommendationAgentPhase.AWAITING_USER
    assert [message.role for message in resumed.session.conversation] == [
        RecommendationAgentMessageRole.ASSISTANT,
        RecommendationAgentMessageRole.USER,
        RecommendationAgentMessageRole.ASSISTANT,
    ]
    assert resumed.session.conversation[0].content == "你喜欢哪类故事？"
    assert repository.load("session-1") == resumed.session
    assert len(repository.saved) == 3
    assert len(created_agents) == 1


@pytest.mark.asyncio
async def test_runner_rejects_unknown_session_without_creating_agent():
    runner, _, created_agents = make_runner(
        LLMResponse(content="不会被调用。"),
    )

    with pytest.raises(
        RecommendationSessionNotFoundError,
        match="missing",
    ):
        await runner.resume("missing", user_message="继续")

    assert created_agents == []


@pytest.mark.asyncio
async def test_runner_retries_saved_pending_turn_without_new_user_message():
    runner, repository, _ = make_runner(
        RuntimeError("provider unavailable"),
        LLMResponse(content="你喜欢哪类故事？"),
    )
    request = RecommendationRequest(origin=RecommendationOrigin.ONBOARDING)

    interrupted = await runner.start(request, session_id="session-1")
    recovered = await runner.retry("session-1")

    assert interrupted.error_code == "model_error"
    assert interrupted.session.conversation == ()
    assert recovered.session.phase is RecommendationAgentPhase.AWAITING_USER
    assert recovered.session.error_code == ""
    assert len(recovered.session.conversation) == 1
    assert repository.load("session-1") == recovered.session


@pytest.mark.asyncio
async def test_runner_handoff_keeps_transcript_and_starts_new_agent_turn():
    runner, repository, _ = make_runner(
        LLMResponse(content="你最近想读哪类故事？"),
        LLMResponse(content="我会根据近期阅读负担重新推荐。"),
    )
    initial = await runner.start(
        RecommendationRequest(origin=RecommendationOrigin.ONBOARDING),
        session_id="session-1",
    )
    repository.save(
        replace(
            initial.session,
            phase=RecommendationAgentPhase.COMPLETED,
        )
    )

    reply = await runner.handoff(
        RecommendationRequest(
            origin=RecommendationOrigin.DIFFICULTY_ALERT
        ),
        session_id="session-1",
        user_message="我想换一本更容易持续阅读的书。",
    )

    assert reply.session.session_id == "session-1"
    assert reply.session.request.origin is RecommendationOrigin.DIFFICULTY_ALERT
    assert [message.role for message in reply.session.conversation] == [
        RecommendationAgentMessageRole.ASSISTANT,
        RecommendationAgentMessageRole.USER,
        RecommendationAgentMessageRole.ASSISTANT,
    ]
    assert reply.session.context_start_index == 1
    assert repository.load("session-1") == reply.session
