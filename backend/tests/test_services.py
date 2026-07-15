import asyncio

import pytest

from superhp_agent.profiles import EnglishNovelProfile
from superhp_agent.profiles.english_novel import BASE_ANNOTATOR_SYSTEM_PROMPT
from superhp_agent.providers.base import LLMProvider, LLMResponse
from superhp_agent.runtime.events import BackendEvent
from superhp_agent.services import (
    AnnotationChunker,
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
            raise RuntimeError("fatal annotation failure")

        try:
            await self.never_complete.wait()
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        return LLMResponse(content="unreachable")

    async def chat_with_retry(self, messages, **kwargs):
        # These tests exercise AnnotatorService task cleanup when an
        # unexpected exception escapes the Provider contract.
        return await self.chat(messages, **kwargs)

    def get_default_model(self):
        return "coordinated"


def test_annotator_service_returns_text_and_extracts_vocabulary():
    async def run_case():
        provider = ScriptedProvider([
            LLMResponse(content="a [[wand|魔杖|noun]] on the [[table|桌子|noun]].")
        ])
        service = AnnotatorService(provider)

        result = await service.annotate_text(
            "a wand on the table.",
            mastered_words=["wand"],
        )

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
        assert "<density_profile" not in user_prompt
        assert "<mastered_words>" in user_prompt
        assert "<mastered_words_policy>" in system_prompt
        assert "<mastered_words_policy>" not in user_prompt
        assert '["wand"]' in user_prompt
        assert "<reader_text>" in user_prompt
        assert provider.kwargs[0]["extra_body"] is None

    asyncio.run(run_case())


def test_annotator_prompt_uses_context_blocks():
    prompt = EnglishNovelProfile().build_annotator_context(
        "a wand on the table",
        mastered_words=["wand"],
    ).render_role("user")

    assert "<density_profile" not in prompt
    assert "<mastered_words>\n[\"wand\"]\n</mastered_words>" in prompt
    assert "<reader_text>\na wand on the table\n</reader_text>" in prompt
    assert "Return only the passage text with any selected inline annotations." in BASE_ANNOTATOR_SYSTEM_PROMPT
    assert "normally use no more than 8 annotations" in BASE_ANNOTATOR_SYSTEM_PROMPT
    assert "never exceed 15 annotations" in BASE_ANNOTATOR_SYSTEM_PROMPT
    assert "[[exact source span|context-specific Chinese gloss|pos]]" in BASE_ANNOTATOR_SYSTEM_PROMPT
    assert "<annotation_examples>" in BASE_ANNOTATOR_SYSTEM_PROMPT


def test_annotator_base_context_excludes_reader_text():
    context = EnglishNovelProfile().build_annotator_base_context(mastered_words=["wand"])

    user_prompt = context.render_role("user")
    system_prompt = context.render_role("system")

    assert "<density_profile" not in user_prompt
    assert "<mastered_words>\n[\"wand\"]\n</mastered_words>" in user_prompt
    assert "<mastered_words_policy>" in system_prompt
    assert "<mastered_words_policy>" not in user_prompt
    assert "<reader_text>" not in user_prompt


def test_annotator_service_deduplicates_vocabulary():
    async def run_case():
        provider = ScriptedProvider([
            LLMResponse(content="a [[wand|魔杖|noun]] and another [[wand|魔杖|noun]].")
        ])
        service = AnnotatorService(provider)

        result = await service.annotate_text("a wand and another wand.")

        assert [item.word for item in result.vocabulary] == ["wand"]

    asyncio.run(run_case())


def test_annotator_service_degrades_legacy_two_part_model_markers():
    async def run_case():
        provider = ScriptedProvider([
            LLMResponse(content="a [[wand|魔杖]] and a [[spell|咒语|noun]].")
        ])
        service = AnnotatorService(provider)

        result = await service.annotate_text("a wand and a spell")

        assert result.annotated_text == "a wand and a spell"
        assert result.vocabulary == []
        assert result.issues[0].code == "malformed_marker"

    asyncio.run(run_case())


def test_annotator_service_strips_code_fence():
    async def run_case():
        provider = ScriptedProvider([
            LLMResponse(content="```\na [[wand|魔杖|noun]] on the table\n```")
        ])
        service = AnnotatorService(provider)

        result = await service.annotate_text("a wand on the table")

        assert result.annotated_text == "a [[wand|魔杖|noun]] on the table"
        assert result.vocabulary[0].word == "wand"

    asyncio.run(run_case())


def test_annotator_service_recovers_legacy_json_shape():
    async def run_case():
        provider = ScriptedProvider([
            LLMResponse(
                content=(
                    '{ "annotated_text": "# Chapter One\n\n'
                    'a [[wand|魔杖|noun]] on the table", '
                    '"extracted_vocabulary": [] }'
                )
            )
        ])
        service = AnnotatorService(provider)

        result = await service.annotate_text("# Chapter One\n\na wand on the table")

        assert result.annotated_text == "# Chapter One\n\na [[wand|魔杖|noun]] on the table"
        assert result.vocabulary[0].word == "wand"

    asyncio.run(run_case())


def test_annotator_service_degrades_empty_response():
    async def run_case():
        provider = ScriptedProvider([LLMResponse(content="")])
        service = AnnotatorService(provider)

        result = await service.annotate_text("a wand")

        assert result.annotated_text == "a wand"
        assert result.fully_degraded
        assert result.issues[0].code == "empty_output"

    asyncio.run(run_case())


def test_annotator_service_degrades_provider_failure_and_emits_category():
    async def run_case():
        provider = ScriptedProvider([
            LLMResponse(
                content="provider unavailable",
                finish_reason="error",
                error_should_retry=False,
            )
        ])
        events = EventCollector()
        service = AnnotatorService(provider)

        result = await service.annotate_text(
            "a wand",
            event_sink=events,
            request_id="r-provider-fallback",
        )

        assert result.annotated_text == "a wand"
        assert result.fully_degraded
        assert result.issues[0].category == "provider"
        degraded = next(
            event for event in events.events if event.type == "annotation.degraded"
        )
        assert degraded.payload["category"] == "provider"
        assert degraded.payload["code"] == "provider_failed"
        assert degraded.payload["chunk_index"] == 1

    asyncio.run(run_case())


def test_annotator_service_keeps_valid_chunks_around_degraded_chunk():
    async def run_case():
        provider = ScriptedProvider([
            LLMResponse(content="first [[part|部分|noun]]"),
            LLMResponse(
                content="provider unavailable",
                finish_reason="error",
                error_should_retry=False,
            ),
            LLMResponse(content="third [[part|部分|noun]]"),
        ])
        service = AnnotatorService(
            provider,
            chunker=AnnotationChunker(max_chunk_words=2),
            max_concurrency=1,
        )

        result = await service.annotate_text(
            "first part\n\nsecond part\n\nthird part"
        )

        assert result.annotated_text == (
            "first [[part|部分|noun]]\n\n"
            "second part\n\n"
            "third [[part|部分|noun]]"
        )
        assert result.validated_chunk_count == 2
        assert result.total_chunk_count == 3
        assert result.issues[0].chunk_index == 2
        assert not result.fully_degraded

    asyncio.run(run_case())


def test_annotator_service_emits_model_retry_event():
    async def run_case():
        provider = ScriptedProvider([
            LLMResponse(content="timeout", finish_reason="error", error_kind="timeout"),
            LLMResponse(content="[[ok|好的|adjective]]"),
        ])
        provider._RETRY_DELAYS = (0.0,)
        events = EventCollector()
        service = AnnotatorService(provider)

        result = await service.annotate_text("ok", event_sink=events, request_id="r-retry")

        assert result.annotated_text == "[[ok|好的|adjective]]"
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
            LLMResponse(content="a [[wand|魔杖|noun]] on the table")
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
            LLMResponse(content="first [[paragraph|段落|noun]]."),
            LLMResponse(content="second [[paragraph|段落|noun]]."),
            LLMResponse(content="third [[paragraph|段落|noun]]."),
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
            "first [[paragraph|段落|noun]].\n\n"
            "second [[paragraph|段落|noun]].\n\n"
            "third [[paragraph|段落|noun]]."
        )
        assert [item.word for item in result.vocabulary] == ["paragraph"]
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


def test_annotator_service_reuses_chapter_mastered_words_for_all_chunks():
    async def run_case():
        provider = ScriptedProvider([
            LLMResponse(content="first paragraph."),
            LLMResponse(content="second paragraph."),
        ])
        service = AnnotatorService(
            provider,
            chunker=AnnotationChunker(max_chunk_words=3),
            max_concurrency=1,
        )

        await service.annotate_text(
            "first paragraph.\n\nsecond paragraph.",
            mastered_words=["first", "second"],
        )

        prompts = [messages[1]["content"] for messages in provider.messages]
        mastered_block = '<mastered_words>\n["first", "second"]\n</mastered_words>'
        assert mastered_block in prompts[0]
        assert mastered_block in prompts[1]
        assert prompts[0].split("<reader_text>", 1)[0] == prompts[1].split(
            "<reader_text>", 1
        )[0]

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


def test_annotator_service_degrades_truncated_output():
    async def run_case():
        provider = ScriptedProvider([
            LLMResponse(content="partial text", finish_reason="length"),
        ])
        service = AnnotatorService(provider)

        result = await service.annotate_text("a wand on the table")

        assert result.annotated_text == "a wand on the table"
        assert result.fully_degraded
        assert result.issues[0].code == "truncated_output"

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


def test_lookup_service_retries_parseable_json_with_missing_required_fields():
    async def run_case():
        provider = ScriptedProvider([
            LLMResponse(content='{"word":"spell","word_cn":"","pos":"noun","sentence_cn":""}'),
            LLMResponse(content='{"word":"changed","word_cn":"咒语","pos":"noun","sentence_cn":"他念了一个咒语。"}'),
        ])
        service = WordLookupService(provider)

        result = await service.lookup("spell", "He cast a spell.")

        assert len(provider.messages) == 2
        assert result["word"] == "spell"
        assert result["word_cn"] == "咒语"
        assert "required JSON fields" in provider.messages[1][1]["content"]

    asyncio.run(run_case())


def test_lookup_service_requires_sentence_translation_when_context_is_given():
    async def run_case():
        provider = ScriptedProvider([
            LLMResponse(content='{"word":"spell","word_cn":"咒语","pos":"noun"}'),
            LLMResponse(content='{"word":"spell","word_cn":"咒语","pos":"noun","sentence_cn":"他念了一个咒语。"}'),
        ])
        service = WordLookupService(provider)

        result = await service.lookup("spell", "He cast a spell.")

        assert len(provider.messages) == 2
        assert result["sentence_cn"] == "他念了一个咒语。"

    asyncio.run(run_case())


def test_lookup_service_allows_empty_sentence_translation_without_context():
    async def run_case():
        provider = ScriptedProvider([
            LLMResponse(content='{"word":"spell","word_cn":"咒语","pos":"noun"}'),
        ])
        service = WordLookupService(provider)

        result = await service.lookup("spell", "")

        assert result["sentence_cn"] == ""

    asyncio.run(run_case())


def test_lookup_service_raises_on_provider_error():
    async def run_case():
        provider = ScriptedProvider([LLMResponse(content="Error: nope", finish_reason="error")])
        service = WordLookupService(provider)

        with pytest.raises(RuntimeError):
            await service.lookup("spell", "He cast a spell.")

    asyncio.run(run_case())
