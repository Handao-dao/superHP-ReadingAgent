"""Tests for the specialized recommendation Companion Episode boundary."""

import pytest

from superhp_agent.agent_tools import ToolRegistry
from superhp_agent.agents import (
    BookRecommendationAgent,
    RecommendationContextBuilder,
)
from superhp_agent.application import RecommendationEpisodeRunner
from superhp_agent.contracts import (
    BookRecommendationHandoff,
    BookSnapshot,
    LLMResponse,
    ReadingCompanionEpisodeTrigger,
    ReadingCompanionMessageRole,
    ReadingDifficultyEvidence,
    RecommendationAgentPhase,
    RecommendationOrigin,
    RecommendationRequest,
)


class ScriptedProvider:
    def __init__(self, *responses):
        self.responses = list(responses)

    async def chat_with_retry(self, messages, *, tools=None, **kwargs):
        del messages, tools, kwargs
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class UnusedTool:
    description = "Unused test tool."
    input_schema = {"type": "object"}

    def __init__(self, name):
        self.name = name

    async def run(self, **arguments):
        del arguments
        raise AssertionError("tool should not run in this test")


def make_runner(*responses):
    created = []

    def factory():
        agent = BookRecommendationAgent(
            ScriptedProvider(*responses),
            RecommendationContextBuilder(),
            ToolRegistry(
                (
                    UnusedTool("search_local_book_catalog"),
                    UnusedTool("present_book_recommendations"),
                    UnusedTool("select_recommended_book"),
                )
            ),
        )
        created.append(agent)
        return agent

    return RecommendationEpisodeRunner(
        factory,
        reader_key="reader-1",
    ), created


@pytest.mark.asyncio
async def test_runner_projects_onboarding_and_resumed_messages():
    runner, created = make_runner(
        LLMResponse(content="你喜欢哪类故事？"),
        LLMResponse(content="我会优先寻找节奏明快的侦探小说。"),
    )
    first = await runner.start(
        RecommendationRequest(origin=RecommendationOrigin.ONBOARDING),
        session_id="session-1",
    )
    resumed = await runner.resume(
        first.recommendation.session,
        user_message="我喜欢侦探故事。",
    )

    assert first.companion.episode.trigger is (
        ReadingCompanionEpisodeTrigger.ONBOARDING
    )
    assert first.companion.session.reader_key == "reader-1"
    assert first.companion.messages[0].role is (
        ReadingCompanionMessageRole.ASSISTANT
    )
    assert resumed.recommendation.session.phase is (
        RecommendationAgentPhase.AWAITING_USER
    )
    assert [item.role for item in resumed.companion.messages] == [
        ReadingCompanionMessageRole.ASSISTANT,
        ReadingCompanionMessageRole.USER,
        ReadingCompanionMessageRole.ASSISTANT,
    ]
    assert resumed.message == "我会优先寻找节奏明快的侦探小说。"
    assert len(created) == 1
    assert created[0].allowed_tools == (
        "search_local_book_catalog",
        "present_book_recommendations",
        "select_recommended_book",
    )


@pytest.mark.asyncio
async def test_runner_retry_reuses_empty_recoverable_episode_identity():
    runner, _ = make_runner(
        RuntimeError("provider unavailable"),
        LLMResponse(content="你通常喜欢什么类型的故事？"),
    )
    interrupted = await runner.start(
        RecommendationRequest(origin=RecommendationOrigin.USER_REQUEST),
        session_id="session-1",
    )
    recovered = await runner.retry(interrupted.recommendation.session)

    assert interrupted.companion.messages == ()
    assert interrupted.companion.episode.episode_id == (
        recovered.companion.episode.episode_id
    )
    assert recovered.companion.messages[0].content == (
        "你通常喜欢什么类型的故事？"
    )


@pytest.mark.asyncio
async def test_difficulty_handoff_opens_a_distinct_episode_boundary():
    runner, _ = make_runner(
        LLMResponse(content="你喜欢哪类故事？"),
        LLMResponse(content="我会结合最近三章的阅读负担重新推荐。"),
    )
    onboarding = await runner.start(
        RecommendationRequest(origin=RecommendationOrigin.ONBOARDING),
        session_id="session-1",
    )
    difficulty = await runner.handoff(
        RecommendationRequest(
            origin=RecommendationOrigin.DIFFICULTY_ALERT,
            handoff=BookRecommendationHandoff(
                current_book=BookSnapshot(
                    book_id="book-1",
                    title="Current Book",
                ),
                evidence=ReadingDifficultyEvidence(
                    observed_word_count=6000,
                    observed_chapter_count=3,
                    lookup_density=16.0,
                ),
            ),
        ),
        previous=onboarding.recommendation.session,
        user_message="我想换一本更容易持续阅读的书。",
    )

    assert difficulty.companion.session.session_id == "session-1"
    assert difficulty.companion.episode.trigger is (
        ReadingCompanionEpisodeTrigger.DIFFICULTY_ALERT
    )
    assert difficulty.companion.episode.book_id == "book-1"
    assert difficulty.companion.episode.episode_id != (
        onboarding.companion.episode.episode_id
    )
    assert [item.content for item in difficulty.companion.messages] == [
        "我想换一本更容易持续阅读的书。",
        "我会结合最近三章的阅读负担重新推荐。",
    ]
