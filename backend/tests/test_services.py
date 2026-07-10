import asyncio

import pytest

from superhp_agent.prompts import (
    BASE_ANNOTATOR_SYSTEM_PROMPT,
    build_annotator_base_context,
    build_annotator_user_prompt,
)
from superhp_agent.providers.base import LLMProvider, LLMResponse
from superhp_agent.runtime.events import BackendEvent
from superhp_agent.services import (
    AnnotationChunker,
    AnnotationTruncatedError,
    AnnotatorService,
    WordLookupService,
)


class EventCollector:
    def __init__(self):
        self.events = []

    async def emit_event(self, event: BackendEvent):
        self.events.append(event)


class ScriptedProvider(LLMProvider):
    def __init__(self, responses):
        super().__init__()
        self.responses = list(responses)
        self.messages = []
        self.kwargs = []

    async def chat(self, messages, **kwargs):
        self.messages.append(messages)
        self.kwargs.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    def get_default_model(self):
        return "scripted"


class CoordinatedProvider(LLMProvider):
    """Hold concurrent calls so cancellation behavior can be asserted."""

    def __init__(self, *, call_count: int, fail_first: bool = False):
        super().__init__()
        self.call_count = call_count
        self.fail_first = fail_first
        self.started = 0
        self.cancelled = 0
        self.all_started = asyncio.Event()
        self.never_complete = asyncio.Event()

    async def chat(self, messages, **kwargs):
        self.started += 1
        call_number = self.started
        if self.started == self.call_count:
            self.all_started.set()
        await self.all_started.wait()

        if self.fail_first and call_number == 1:
            return LLMResponse(
                content="fatal annotation failure",
                finish_reason="error",
                error_should_retry=False,
            )

        try:
            await self.never_complete.wait()
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        return LLMResponse(content="unreachable")

    def get_default_model(self):
        return "coordinated"


def test_annotator_service_returns_text_and_extracts_vocabulary():
    async def run_case():
        provider = ScriptedProvider([
            LLMResponse(content="a [[wand|魔杖|noun]] on the [[table|桌子|noun]].")
        ])
        service = AnnotatorService(provider)

        result = await service.annotate_text("a wand on the table", mastered_words=["owl"], level="beginner")

        assert result.annotated_text == "a [[wand|魔杖|noun]] on the [[table|桌子|noun]]."
        assert [(item.word, item.translation, item.pos) for item in result.vocabulary] == [
            ("wand", "魔杖", "noun"),
            ("table", "桌子", "noun"),
        ]
        assert [message["role"] for message in provider.messages[0]] == ["system", "user"]
        system_prompt = provider.messages[0][0]["content"]
        user_prompt = provider.messages[0][1]["content"]
        assert "<system_policy>" in system_prompt
        assert "<annotation_contract>" in system_prompt
        assert "<annotation_examples>" in system_prompt
        assert "<output_contract>" in system_prompt
        assert '<density_profile level="beginner" ui="H" density="high">' in user_prompt
        assert "<mastered_words>" in user_prompt
        assert "<mastered_words_policy>" in user_prompt
        assert '["owl"]' in user_prompt
        assert "<reader_text>" in user_prompt
        assert provider.kwargs[0]["extra_body"] is None

    asyncio.run(run_case())


def test_annotator_prompt_uses_context_blocks():
    prompt = build_annotator_user_prompt(
        "a wand on the table",
        mastered_words=["wand"],
        level="advanced",
    )

    assert '<density_profile level="advanced" ui="L" density="low">' in prompt
    assert "Target density: about 2%-6% of meaningful content words" in prompt
    assert "<mastered_words>\n[\"wand\"]\n</mastered_words>" in prompt
    assert "<reader_text>\na wand on the table\n</reader_text>" in prompt
    assert "Return only the annotated passage text." in BASE_ANNOTATOR_SYSTEM_PROMPT
    assert "[[word or expression|中文翻译|pos]]" in BASE_ANNOTATOR_SYSTEM_PROMPT
    assert "<annotation_examples>" in BASE_ANNOTATOR_SYSTEM_PROMPT


def test_annotator_base_context_excludes_reader_text():
    context = build_annotator_base_context(mastered_words=["wand"], level="intermediate")

    user_prompt = context.render_role("user")

    assert '<density_profile level="intermediate" ui="M" density="medium">' in user_prompt
    assert "<mastered_words>\n[\"wand\"]\n</mastered_words>" in user_prompt
    assert "<mastered_words_policy>" in user_prompt
    assert "<reader_text>" not in user_prompt


def test_annotator_service_deduplicates_vocabulary():
    async def run_case():
        provider = ScriptedProvider([
            LLMResponse(content="a [[wand|魔杖]] and another [[wand|魔杖]].")
        ])
        service = AnnotatorService(provider)

        result = await service.annotate_text("a wand and another wand")

        assert [item.word for item in result.vocabulary] == ["wand"]

    asyncio.run(run_case())


def test_annotator_service_keeps_legacy_two_part_markers():
    async def run_case():
        provider = ScriptedProvider([
            LLMResponse(content="a [[wand|魔杖]] and a [[spell|咒语|noun]].")
        ])
        service = AnnotatorService(provider)

        result = await service.annotate_text("a wand and a spell")

        assert [(item.word, item.translation, item.pos) for item in result.vocabulary] == [
            ("wand", "魔杖", "other"),
            ("spell", "咒语", "noun"),
        ]

    asyncio.run(run_case())


def test_annotator_service_strips_code_fence():
    async def run_case():
        provider = ScriptedProvider([
            LLMResponse(content="```\na [[wand|魔杖]] on the table\n```")
        ])
        service = AnnotatorService(provider)

        result = await service.annotate_text("a wand on the table")

        assert result.annotated_text == "a [[wand|魔杖]] on the table"
        assert result.vocabulary[0].word == "wand"

    asyncio.run(run_case())


def test_annotator_service_recovers_legacy_json_shape():
    async def run_case():
        provider = ScriptedProvider([
            LLMResponse(
                content=(
                    '{ "annotated_text": "# Chapter One\n\n'
                    'a [[wand|魔杖]] on the table", '
                    '"extracted_vocabulary": [] }'
                )
            )
        ])
        service = AnnotatorService(provider)

        result = await service.annotate_text("a wand")

        assert result.annotated_text == "# Chapter One\n\na [[wand|魔杖]] on the table"
        assert result.vocabulary[0].word == "wand"

    asyncio.run(run_case())


def test_annotator_service_raises_on_empty_response():
    async def run_case():
        provider = ScriptedProvider([LLMResponse(content="")])
        service = AnnotatorService(provider)

        with pytest.raises(ValueError, match="译注文本"):
            await service.annotate_text("a wand")

    asyncio.run(run_case())


def test_annotator_service_emits_model_retry_event():
    async def run_case():
        provider = ScriptedProvider([
            LLMResponse(content="timeout", finish_reason="error", error_kind="timeout"),
            LLMResponse(content="a [[wand|魔杖]] on the table"),
        ])
        provider._RETRY_DELAYS = (0.0,)
        events = EventCollector()
        service = AnnotatorService(provider)

        result = await service.annotate_text("ok", event_sink=events, request_id="r-retry")

        assert result.annotated_text == "a [[wand|魔杖]] on the table"
        retry_event = next(
            event for event in events.events if event.type == "annotation.model_retry"
        )
        assert retry_event.request_id == "r-retry"
        assert retry_event.payload["chunk_index"] == 1
        assert "retrying" in retry_event.payload["message"]

    asyncio.run(run_case())


def test_annotator_service_emits_consistent_progress_for_one_chunk():
    async def run_case():
        provider = ScriptedProvider([
            LLMResponse(content="a [[wand|魔杖]] on the table")
        ])
        events = EventCollector()
        service = AnnotatorService(provider)

        await service.annotate_text(
            "a wand on the table",
            event_sink=events,
            request_id="r-one-chunk",
        )

        progress = [
            event.payload
            for event in events.events
            if event.type == "annotation.progress"
        ]
        assert [(item["current"], item["total"]) for item in progress] == [
            (0, 1),
            (1, 1),
        ]
        assert "chunk_index" not in progress[0]
        assert progress[1]["chunk_index"] == 1
        assert progress[1]["message"] == "Completed 1 of 1 sections."

    asyncio.run(run_case())




def test_annotation_chunker_estimates_words_chinese_characters_and_punctuation():
    assert AnnotationChunker._measure("Hello, magic world!") == 5
    assert AnnotationChunker._measure("学而时习之。") == 6
    assert AnnotationChunker._measure("magic 魔法!") == 4


def test_annotation_chunker_packs_complete_paragraphs_up_to_limit():
    paragraphs = [" ".join(f"p{idx}w{word}" for word in range(3)) for idx in range(5)]
    chunks = AnnotationChunker(max_chunk_words=6).split("\n\n".join(paragraphs))

    assert [chunk.text for chunk in chunks] == [
        "\n\n".join(paragraphs[:2]),
        "\n\n".join(paragraphs[2:4]),
        paragraphs[4],
    ]
    assert all(AnnotationChunker._measure(chunk.text) <= 6 for chunk in chunks)


def test_annotation_chunker_rejects_one_paragraph_over_limit():
    with pytest.raises(ValueError, match="exceeds the annotation input limit"):
        AnnotationChunker(max_chunk_words=4).split("one two three four five")


def test_annotator_service_chunks_long_text_and_merges_in_order():
    async def run_case():
        provider = ScriptedProvider([
            LLMResponse(content="first [[wand|魔杖]] paragraph."),
            LLMResponse(content="second [[owl|猫头鹰]] paragraph."),
            LLMResponse(content="third [[cloak|斗篷]] paragraph."),
        ])
        events = EventCollector()
        service = AnnotatorService(
            provider,
            chunker=AnnotationChunker(max_chunk_words=3),
            max_concurrency=1,
        )

        result = await service.annotate_text(
            "first paragraph.\n\nsecond paragraph.\n\nthird paragraph.",
            event_sink=events,
            request_id="r-chunks",
        )

        assert result.annotated_text == (
            "first [[wand|魔杖]] paragraph.\n\n"
            "second [[owl|猫头鹰]] paragraph.\n\n"
            "third [[cloak|斗篷]] paragraph."
        )
        assert [item.word for item in result.vocabulary] == ["wand", "owl", "cloak"]
        progress_events = [
            event for event in events.events if event.type == "annotation.progress"
        ]
        assert progress_events[0].payload["current"] == 0
        assert progress_events[0].payload["total"] == 3
        assert "chunk_index" not in progress_events[0].payload
        assert progress_events[-1].payload["current"] == 3
        assert [event.payload["chunk_index"] for event in progress_events[1:]] == [
            1,
            2,
            3,
        ]
        assert progress_events[-1].payload["message"] == "Completed 3 of 3 sections."
        user_prompts = [messages[1]["content"] for messages in provider.messages]
        stable_prefixes = [prompt.split("<reader_text>", 1)[0] for prompt in user_prompts]
        assert len(set(stable_prefixes)) == 1
        assert "first paragraph." in user_prompts[0]
        assert "second paragraph." in user_prompts[1]
        assert "third paragraph." in user_prompts[2]

    asyncio.run(run_case())


def test_annotator_service_cancels_and_awaits_siblings_when_one_chunk_fails():
    async def run_case():
        provider = CoordinatedProvider(call_count=3, fail_first=True)
        service = AnnotatorService(
            provider,
            chunker=AnnotationChunker(max_chunk_words=2),
            max_concurrency=3,
        )

        with pytest.raises(RuntimeError, match="fatal annotation failure"):
            await service.annotate_text("first part\n\nsecond part\n\nthird part")

        assert provider.cancelled == 2

    asyncio.run(run_case())


def test_annotator_service_cleans_up_chunks_when_parent_is_cancelled():
    async def run_case():
        provider = CoordinatedProvider(call_count=3)
        service = AnnotatorService(
            provider,
            chunker=AnnotationChunker(max_chunk_words=2),
            max_concurrency=3,
        )
        annotation = asyncio.create_task(
            service.annotate_text("first part\n\nsecond part\n\nthird part")
        )
        await provider.all_started.wait()

        annotation.cancel()
        with pytest.raises(asyncio.CancelledError):
            await annotation

        assert provider.cancelled == 3

    asyncio.run(run_case())


def test_annotator_service_rejects_truncated_output():
    async def run_case():
        provider = ScriptedProvider([
            LLMResponse(content="partial text", finish_reason="length"),
        ])
        service = AnnotatorService(provider)

        with pytest.raises(AnnotationTruncatedError):
            await service.annotate_text("a wand on the table")

    asyncio.run(run_case())

def test_lookup_service_parses_lookup_result():
    async def run_case():
        provider = ScriptedProvider([
            LLMResponse(content='{"word":"spell","word_cn":"咒语","pos":"noun","sentence_cn":"他念了一个咒语。"}')
        ])
        service = WordLookupService(provider)

        result = await service.lookup("spell", "He cast a spell.")

        assert result == {
            "word": "spell",
            "word_cn": "咒语",
            "pos": "noun",
            "sentence_cn": "他念了一个咒语。",
        }

    asyncio.run(run_case())


def test_lookup_service_normalizes_pos_alias():
    async def run_case():
        provider = ScriptedProvider([
            LLMResponse(content='{"word":"quickly","word_cn":"迅速地","pos":"adv","sentence_cn":"他迅速地走了。"}')
        ])
        service = WordLookupService(provider)

        result = await service.lookup("quickly", "He walked quickly.")

        assert result["pos"] == "adverb"

    asyncio.run(run_case())


def test_lookup_service_raises_on_provider_error():
    async def run_case():
        provider = ScriptedProvider([LLMResponse(content="Error: nope", finish_reason="error")])
        service = WordLookupService(provider)

        with pytest.raises(RuntimeError):
            await service.lookup("spell", "He cast a spell.")

    asyncio.run(run_case())
