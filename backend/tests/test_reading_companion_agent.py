"""Tests for the manual reading companion observe-model-tool Loop."""

import json

import pytest

from superhp_agent.agent_tools import ToolRegistry
from superhp_agent.agents import (
    ReadingCompanionAgent,
    ReadingCompanionContextBuilder,
    ReadingCompanionStateError,
)
from superhp_agent.contracts import (
    AgentToolExecutionContext,
    LLMResponse,
    LLMToolCall,
    PreviousReadingScope,
    ReadingCompanionEpisode,
    ReadingCompanionEpisodeTrigger,
    ReadingCompanionMessage,
    ReadingCompanionMessageRole,
    ReadingCompanionRunState,
)


class ScriptedProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def chat_with_retry(self, messages, *, tools=None, on_retry_wait=None):
        self.calls.append({"messages": messages, "tools": tools})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class RecordingTool:
    description = "A test reading-history tool."
    input_schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
    }

    def __init__(self, name):
        self.name = name
        self.calls = []

    async def run(self, *, context=None, **arguments):
        self.calls.append({"context": context, "arguments": arguments})
        return {
            "tool": self.name,
            "ok": True,
            "found": True,
            "matches": [{"chapter_no": 1}],
        }


def _state() -> ReadingCompanionRunState:
    message = ReadingCompanionMessage(
        message_id="message-1",
        session_id="session-1",
        episode_id="episode-1",
        role=ReadingCompanionMessageRole.USER,
        content="斯内普以前出现过吗？",
    )
    episode = ReadingCompanionEpisode(
        episode_id="episode-1",
        session_id="session-1",
        trigger=ReadingCompanionEpisodeTrigger.MANUAL_READING,
        start_message_id=message.message_id,
        book_id="book-1",
        chapter_id="book-1-ch02",
        unit_id="book-1-ch2",
        selected_text="Snape looked at Harry.",
    )
    return ReadingCompanionRunState(
        episode=episode,
        conversation=(message,),
    )


def _tool_context() -> AgentToolExecutionContext:
    return AgentToolExecutionContext(
        session_id="session-1",
        episode_id="episode-1",
        language_id="en",
        previous_reading_scope=PreviousReadingScope(
            book_id="book-1",
            current_chapter_id="book-1-ch02",
            current_chapter_no=2,
        ),
    )


def _agent(provider):
    previous_tool = RecordingTool("search_previous_chapters")
    vocabulary_tool = RecordingTool("search_vocabulary_history")
    agent = ReadingCompanionAgent(
        provider,
        ReadingCompanionContextBuilder(),
        ToolRegistry((previous_tool, vocabulary_tool)),
    )
    return agent, previous_tool, vocabulary_tool


@pytest.mark.asyncio
async def test_companion_answers_directly_with_reading_runtime_context():
    provider = ScriptedProvider(
        [LLMResponse(content="这段文字表现出斯内普正在注意哈利。")]
    )
    agent, _, _ = _agent(provider)

    reply = await agent.run(
        _state(),
        tool_context=_tool_context(),
        book_title="Book One",
        chapter_title="Chapter Two",
        chapter_no=2,
    )

    assert reply.message.startswith("这段文字")
    assert [
        message.role for message in reply.state.conversation
    ] == [
        ReadingCompanionMessageRole.USER,
        ReadingCompanionMessageRole.ASSISTANT,
    ]
    provider_call = provider.calls[0]
    assert [
        tool["function"]["name"] for tool in provider_call["tools"]
    ] == [
        "search_previous_chapters",
        "search_vocabulary_history",
    ]
    assert "不要尝试通过历史工具检索当前或未来章节" in (
        provider_call["messages"][0]["content"]
    )
    assert "Snape looked at Harry." not in (
        provider_call["messages"][0]["content"]
    )
    assert "Snape looked at Harry." in (
        provider_call["messages"][1]["content"]
    )


@pytest.mark.asyncio
async def test_companion_executes_tool_then_continues_model_reasoning():
    tool_call = LLMToolCall(
        id="call-1",
        name="search_previous_chapters",
        arguments={"query": "Snape"},
    )
    provider = ScriptedProvider(
        (
            LLMResponse(
                content=None,
                finish_reason="tool_calls",
                tool_calls=(tool_call,),
            ),
            LLMResponse(
                content="是的，他在第一章已经出现过。",
            ),
        )
    )
    agent, previous_tool, _ = _agent(provider)
    tool_context = _tool_context()

    reply = await agent.run(
        _state(),
        tool_context=tool_context,
        book_title="Book One",
        chapter_title="Chapter Two",
        chapter_no=2,
    )

    assert reply.message == "是的，他在第一章已经出现过。"
    assert [
        message.role for message in reply.state.conversation
    ] == [
        ReadingCompanionMessageRole.USER,
        ReadingCompanionMessageRole.ASSISTANT,
        ReadingCompanionMessageRole.TOOL,
        ReadingCompanionMessageRole.ASSISTANT,
    ]
    assert previous_tool.calls == [
        {
            "context": tool_context,
            "arguments": {"query": "Snape"},
        }
    ]
    tool_message = reply.state.conversation[2]
    assert json.loads(tool_message.content)["found"] is True
    assert tool_message.tool_call_id == "call-1"
    assert provider.calls[1]["messages"][-1]["role"] == "tool"


@pytest.mark.asyncio
async def test_companion_continuation_requires_and_accepts_new_user_turn():
    provider = ScriptedProvider(
        (
            LLMResponse(content="第一次回答。"),
            LLMResponse(content="第二次回答。"),
        )
    )
    agent, _, _ = _agent(provider)
    first = await agent.run(
        _state(),
        tool_context=_tool_context(),
        book_title="Book One",
        chapter_title="Chapter Two",
        chapter_no=2,
    )

    with pytest.raises(ReadingCompanionStateError):
        await agent.run(
            first.state,
            tool_context=_tool_context(),
            book_title="Book One",
            chapter_title="Chapter Two",
            chapter_no=2,
        )

    second = await agent.run(
        first.state,
        tool_context=_tool_context(),
        book_title="Book One",
        chapter_title="Chapter Two",
        chapter_no=2,
        user_message="那他当时做了什么？",
    )

    assert second.message == "第二次回答。"
    assert second.state.conversation[-2].role is (
        ReadingCompanionMessageRole.USER
    )
    assert second.state.tool_call_count == 0


@pytest.mark.asyncio
async def test_companion_keeps_provider_failure_recoverable():
    provider = ScriptedProvider([RuntimeError("provider unavailable")])
    agent, _, _ = _agent(provider)

    reply = await agent.run(
        _state(),
        tool_context=_tool_context(),
        book_title="Book One",
        chapter_title="Chapter Two",
        chapter_no=2,
    )

    assert reply.error_code == "model_error"
    assert reply.state.error_code == "model_error"
    assert len(reply.state.conversation) == 1


@pytest.mark.asyncio
async def test_companion_rejects_tool_context_from_another_episode():
    provider = ScriptedProvider([LLMResponse(content="不应执行")])
    agent, _, _ = _agent(provider)
    mismatched = AgentToolExecutionContext(
        session_id="session-1",
        episode_id="another-episode",
        language_id="en",
        previous_reading_scope=PreviousReadingScope(
            book_id="book-1",
            current_chapter_id="book-1-ch02",
            current_chapter_no=2,
        ),
    )

    with pytest.raises(ReadingCompanionStateError, match="does not match"):
        await agent.run(
            _state(),
            tool_context=mismatched,
            book_title="Book One",
            chapter_title="Chapter Two",
            chapter_no=2,
        )

    assert provider.calls == []
