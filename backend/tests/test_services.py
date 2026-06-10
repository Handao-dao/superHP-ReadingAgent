import asyncio

import pytest

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
        self.events.append(event.as_message())


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


def test_annotator_service_returns_text_and_extracts_vocabulary():
    async def run_case():
        provider = ScriptedProvider([
            LLMResponse(content="a [[wand|魔杖]] on the [[table|桌子]].")
        ])
        service = AnnotatorService(provider)

        result = await service.annotate_text("a wand on the table", mastered_words=["owl"], level="beginner")

        assert result.annotated_text == "a [[wand|魔杖]] on the [[table|桌子]]."
        assert [(item.word, item.translation) for item in result.vocabulary] == [
            ("wand", "魔杖"),
            ("table", "桌子"),
        ]
        assert "Mastered words" in provider.messages[0][1]["content"]
        assert provider.kwargs[0]["extra_body"] is None

    asyncio.run(run_case())


def test_annotator_service_deduplicates_vocabulary():
    async def run_case():
        provider = ScriptedProvider([
            LLMResponse(content="a [[wand|魔杖]] and another [[wand|魔杖]].")
        ])
        service = AnnotatorService(provider)

        result = await service.annotate_text("a wand and another wand")

        assert [item.word for item in result.vocabulary] == ["wand"]

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
        assert events.events[0]["type"] == "annotation.model_retry"
        assert events.events[0]["request_id"] == "r-retry"
        assert "retrying" in events.events[0]["message"]

    asyncio.run(run_case())




def test_annotation_chunker_preserves_long_paragraph_even_over_max_words():
    long_paragraph = " ".join(f"word{i}" for i in range(12))
    chunks = AnnotationChunker(max_chunk_words=5).split(
        f"{long_paragraph}\n\nshort ending."
    )

    assert len(chunks) == 2
    assert chunks[0].text == long_paragraph
    assert len(chunks[0].text.split()) == 12
    assert chunks[1].text == "short ending."


def test_annotation_chunker_seals_chunk_after_crossing_max_words():
    paragraphs = [" ".join(f"p{idx}w{word}" for word in range(3)) for idx in range(5)]
    chunks = AnnotationChunker(max_chunk_words=7).split("\n\n".join(paragraphs))

    assert [chunk.text for chunk in chunks] == [
        "\n\n".join(paragraphs[:3]),
        "\n\n".join(paragraphs[3:]),
    ]
    assert len(chunks[0].text.split()) == 9


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
            chunker=AnnotationChunker(max_chunk_words=1),
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
        progress_events = [event for event in events.events if event["type"] == "annotation.progress"]
        assert progress_events[0]["current"] == 0
        assert progress_events[0]["total"] == 3
        assert progress_events[-1]["current"] == 3
        assert progress_events[-1]["message"] == "Annotating section 3 of 3..."

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
