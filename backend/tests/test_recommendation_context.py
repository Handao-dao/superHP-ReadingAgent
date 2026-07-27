"""Tests for recommendation runtime facts and context-epoch projection."""

from superhp_agent.agents import RecommendationContextBuilder
from superhp_agent.contracts import (
    LLMToolCall,
    RecommendationAgentMessage,
    RecommendationAgentMessageRole,
    RecommendationAgentObservation,
    RecommendationAgentPhase,
    RecommendationOrigin,
    RecommendationRequest,
)


def test_context_keeps_old_visible_dialogue_but_drops_old_tool_protocol():
    old_tool_call = LLMToolCall(
        id="search-old",
        name="search_local_book_catalog",
        arguments={"genres": ["fantasy"]},
    )
    conversation = (
        RecommendationAgentMessage(
            role=RecommendationAgentMessageRole.USER,
            content="我喜欢奇幻小说。",
        ),
        RecommendationAgentMessage(
            role=RecommendationAgentMessageRole.ASSISTANT,
            tool_calls=(old_tool_call,),
        ),
        RecommendationAgentMessage(
            role=RecommendationAgentMessageRole.TOOL,
            content='{"candidates":[{"catalog_id":"old-book"}]}',
            tool_call_id="search-old",
            tool_name="search_local_book_catalog",
        ),
        RecommendationAgentMessage(
            role=RecommendationAgentMessageRole.ASSISTANT,
            content="上一轮给你推荐了两本奇幻小说。",
        ),
        RecommendationAgentMessage(
            role=RecommendationAgentMessageRole.USER,
            content="最近读起来太难了，请重新推荐。",
        ),
    )
    observation = RecommendationAgentObservation(
        request=RecommendationRequest(
            origin=RecommendationOrigin.DIFFICULTY_ALERT
        ),
        phase=RecommendationAgentPhase.COLLECTING_PREFERENCES,
        conversation=conversation,
        observed_catalog_ids=(),
        presented_catalog_ids=(),
        selected_catalog_id="",
        context_start_index=4,
        remaining_tool_calls=3,
    )

    messages = RecommendationContextBuilder().build(observation)

    assert [message["role"] for message in messages] == [
        "system",
        "user",
        "user",
        "assistant",
        "user",
    ]
    assert "old-book" not in str(messages)
    assert "search_local_book_catalog" not in str(messages[2:])
    assert messages[-2] == {
        "role": "assistant",
        "content": "上一轮给你推荐了两本奇幻小说。",
    }
    assert messages[-1] == {
        "role": "user",
        "content": "最近读起来太难了，请重新推荐。",
    }


def test_context_exposes_current_presented_and_selected_catalog_state():
    observation = RecommendationAgentObservation(
        request=RecommendationRequest(origin=RecommendationOrigin.ONBOARDING),
        phase=RecommendationAgentPhase.AWAITING_USER,
        conversation=(),
        observed_catalog_ids=("book-a", "book-b"),
        presented_catalog_ids=("book-b",),
        selected_catalog_id="",
        context_start_index=0,
        remaining_tool_calls=2,
    )

    messages = RecommendationContextBuilder().build(observation)
    runtime_message = messages[1]["content"]

    assert '"presented_catalog_ids": ["book-b"]' in runtime_message
    assert '"selected_catalog_id": ""' in runtime_message
