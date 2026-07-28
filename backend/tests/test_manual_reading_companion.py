"""Tests for the manual reading invocation coordinator."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from superhp_agent.agent_tools import (
    PreviousChapterSearchTool,
    ToolRegistry,
    VocabularyHistorySearchTool,
)
from superhp_agent.agents import (
    ReadingCompanionAgent,
    ReadingCompanionContextBuilder,
)
from superhp_agent.application import (
    ManualReadingCompanionError,
    ManualReadingCompanionRunner,
    PreviousChapterSearchService,
    PreviousReadingScopeBuilder,
    VocabularyHistorySearchService,
)
from superhp_agent.contracts import (
    ChapterReadingCheckpoint,
    LLMResponse,
    LLMToolCall,
    ReadingCompanionMessage,
    ReadingCompanionMessageRole,
    ReadingCompanionReply,
)
from superhp_agent.corpus import ReadingUnit, ReadingUnitDocument


class FakeCorpus:
    def __init__(self, units):
        self.units = list(units)

    def list_units(self):
        return list(self.units)

    def get_unit(self, unit_id):
        unit = next(unit for unit in self.units if unit.id == unit_id)
        body = (
            "Professor Snape looked across the hall."
            if unit.chapter_no == 1
            else "Current chapter text."
        )
        return ReadingUnitDocument(meta=unit, body=body)


class FakeCheckpointRepository:
    def __init__(self, checkpoints):
        self.checkpoints = tuple(checkpoints)

    def list_for_book(self, book_id):
        return tuple(
            checkpoint
            for checkpoint in self.checkpoints
            if checkpoint.book_id == book_id
        )


class RecordingAgent:
    def __init__(self):
        self.calls = []

    async def run(self, state, **kwargs):
        self.calls.append({"state": state, **kwargs})
        assistant = ReadingCompanionMessage(
            message_id=f"assistant-{len(self.calls)}",
            session_id=state.episode.session_id,
            episode_id=state.episode.episode_id,
            role=ReadingCompanionMessageRole.ASSISTANT,
            content="测试回答",
        )
        next_state = replace(
            state,
            conversation=(*state.conversation, assistant),
        )
        return ReadingCompanionReply(
            state=next_state,
            message="测试回答",
        )


class ScriptedProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def chat_with_retry(self, messages, *, tools=None, on_retry_wait=None):
        self.calls.append({"messages": messages, "tools": tools})
        return self.responses.pop(0)


class EmptyVocabularyHistoryRepository:
    def find_encounters(self, **kwargs):
        return ()


def _unit(unit_id: str, chapter_no: int) -> ReadingUnit:
    return ReadingUnit(
        id=unit_id,
        chapter_id=f"book-1-ch{chapter_no:02d}",
        book_id="book-1",
        book_title="Book One",
        chapter_no=chapter_no,
        chapter_title=f"Chapter {chapter_no}",
        section_no=1,
        section_count=1,
        summary="",
        path=Path(f"{unit_id}.md"),
    )


def _runner():
    units = (
        _unit("book-1-ch1", 1),
        _unit("book-1-ch2", 2),
    )
    corpus = FakeCorpus(units)
    checkpoint = ChapterReadingCheckpoint(
        book_id="book-1",
        chapter_id="book-1-ch01",
        chapter_no=1,
        unit_ids=("book-1-ch1",),
        word_count=1000,
        lookup_count=0,
        annotated_lookup_count=0,
    )
    scope_builder = PreviousReadingScopeBuilder(
        corpus,
        FakeCheckpointRepository((checkpoint,)),
    )
    agent = RecordingAgent()
    runner = ManualReadingCompanionRunner(
        corpus,
        scope_builder,
        lambda: agent,
    )
    return runner, corpus, agent


@pytest.mark.asyncio
async def test_manual_runner_freezes_unit_and_builds_trusted_tool_context():
    runner, _, agent = _runner()
    state = runner.start(
        session_id="session-1",
        current_unit_id="book-1-ch2",
        user_message="这个人以前出现过吗？",
        selected_text="A suspicious visitor entered.",
        episode_id="episode-1",
    )

    reply = await runner.run(state)

    assert state.episode.book_id == "book-1"
    assert state.episode.chapter_id == "book-1-ch02"
    assert state.episode.unit_id == "book-1-ch2"
    assert state.episode.selected_text == "A suspicious visitor entered."
    assert reply.message == "测试回答"
    call = agent.calls[0]
    assert call["book_title"] == "Book One"
    assert call["chapter_no"] == 2
    assert call["tool_context"].language_id == "en"
    assert (
        call["tool_context"].previous_reading_scope.searchable_unit_ids
        == ("book-1-ch1",)
    )


@pytest.mark.asyncio
async def test_manual_runner_rejects_unknown_or_stale_frozen_unit():
    runner, corpus, _ = _runner()
    with pytest.raises(ManualReadingCompanionError) as missing:
        runner.start(
            session_id="session-1",
            current_unit_id="missing",
            user_message="你好",
        )
    assert missing.value.code == "no_active_reading"

    state = runner.start(
        session_id="session-1",
        current_unit_id="book-1-ch2",
        user_message="你好",
        episode_id="episode-1",
    )
    corpus.units[1] = replace(
        corpus.units[1],
        chapter_id="book-1-changed",
    )

    with pytest.raises(ManualReadingCompanionError) as stale:
        await runner.run(state)

    assert stale.value.code == "scope_stale"


@pytest.mark.asyncio
async def test_manual_runner_executes_real_scoped_chapter_tool_round():
    units = (
        replace(
            _unit("book-1-ch1", 1),
            summary="Snape first appeared at the feast.",
        ),
        _unit("book-1-ch2", 2),
    )
    corpus = FakeCorpus(units)
    checkpoint = ChapterReadingCheckpoint(
        book_id="book-1",
        chapter_id="book-1-ch01",
        chapter_no=1,
        unit_ids=("book-1-ch1",),
        word_count=1000,
        lookup_count=0,
        annotated_lookup_count=0,
    )
    scope_builder = PreviousReadingScopeBuilder(
        corpus,
        FakeCheckpointRepository((checkpoint,)),
    )
    provider = ScriptedProvider(
        (
            LLMResponse(
                content=None,
                finish_reason="tool_calls",
                tool_calls=(
                    LLMToolCall(
                        id="call-1",
                        name="search_previous_chapters",
                        arguments={"query": "Snape"},
                    ),
                ),
            ),
            LLMResponse(content="是的，他在第一章已经出现过。"),
        )
    )
    registry = ToolRegistry(
        (
            PreviousChapterSearchTool(
                PreviousChapterSearchService(corpus)
            ),
            VocabularyHistorySearchTool(
                VocabularyHistorySearchService(
                    EmptyVocabularyHistoryRepository()
                )
            ),
        )
    )
    runner = ManualReadingCompanionRunner(
        corpus,
        scope_builder,
        lambda: ReadingCompanionAgent(
            provider,
            ReadingCompanionContextBuilder(),
            registry,
        ),
    )
    state = runner.start(
        session_id="session-1",
        current_unit_id="book-1-ch2",
        user_message="斯内普以前出现过吗？",
        episode_id="episode-1",
    )

    reply = await runner.run(state)

    assert reply.message == "是的，他在第一章已经出现过。"
    tool_message = reply.state.conversation[2]
    tool_result = json.loads(tool_message.content)
    assert tool_result["found"] is True
    assert tool_result["matches"][0]["chapter_no"] == 1
    assert provider.calls[1]["messages"][-1]["role"] == "tool"
