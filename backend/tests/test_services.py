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
        assert events.events[0].type == "annotation.model_retry"
        assert events.events[0].request_id == "r-retry"
        assert "retrying" in events.events[0].payload["message"]

    asyncio.run(run_case())




def test_annotation_chunker_hard_splits_long_english_paragraph():
    long_paragraph = " ".join(f"word{i}" for i in range(12))
    source = f"{long_paragraph}\n\nshort ending."
    chunks = AnnotationChunker(max_chunk_words=5).split(source)

    assert [chunk.text for chunk in chunks] == [
        " ".join(f"word{i}" for i in range(5)),
        " ".join(f"word{i}" for i in range(5, 10)),
        "word10 word11\n\nshort ending.",
    ]
    assert all(AnnotationChunker._measure(chunk.text) <= 5 for chunk in chunks)
    assert chunks[0].text + "".join(
        chunk.separator_before + chunk.text for chunk in chunks[1:]
    ) == source


def test_annotation_chunker_never_crosses_hard_limit_when_packing_paragraphs():
    paragraphs = [" ".join(f"p{idx}w{word}" for word in range(3)) for idx in range(5)]
    chunks = AnnotationChunker(max_chunk_words=7).split("\n\n".join(paragraphs))

    assert [chunk.text for chunk in chunks] == [
        "\n\n".join(paragraphs[:2]),
        "\n\n".join(paragraphs[2:4]),
        paragraphs[4],
    ]
    assert all(AnnotationChunker._measure(chunk.text) <= 7 for chunk in chunks)


def test_annotation_chunker_counts_chinese_characters_and_prefers_sentence_end():
    source = "学而时习之。不亦说乎？"
    chunks = AnnotationChunker(max_chunk_words=5).split(source)

    assert [chunk.text for chunk in chunks] == ["学而时习之。", "不亦说乎？"]
    assert all(AnnotationChunker._measure(chunk.text) <= 5 for chunk in chunks)
    assert chunks[0].text + "".join(
        chunk.separator_before + chunk.text for chunk in chunks[1:]
    ) == source


def test_annotation_chunker_hard_splits_unpunctuated_chinese_text():
    chunks = AnnotationChunker(max_chunk_words=4).split("天地玄黄宇宙洪荒日月盈昃")

    assert [chunk.text for chunk in chunks] == ["天地玄黄", "宇宙洪荒", "日月盈昃"]
    assert "".join(chunk.text for chunk in chunks) == "天地玄黄宇宙洪荒日月盈昃"


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
            chunker=AnnotationChunker(max_chunk_words=2),
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
        assert progress_events[-1].payload["current"] == 3
        assert progress_events[-1].payload["message"] == "Annotating section 3 of 3..."
        user_prompts = [messages[1]["content"] for messages in provider.messages]
        stable_prefixes = [prompt.split("<reader_text>", 1)[0] for prompt in user_prompts]
        assert len(set(stable_prefixes)) == 1
        assert "first paragraph." in user_prompts[0]
        assert "second paragraph." in user_prompts[1]
        assert "third paragraph." in user_prompts[2]

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
