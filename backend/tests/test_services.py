import asyncio

import pytest

from superhp_agent.providers.base import LLMProvider, LLMResponse
from superhp_agent.services import AnnotatorService, WordLookupService


class ScriptedProvider(LLMProvider):
    def __init__(self, responses):
        super().__init__()
        self.responses = list(responses)
        self.messages = []

    async def chat(self, messages, **kwargs):
        self.messages.append(messages)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    def get_default_model(self):
        return "scripted"


def test_annotator_service_parses_annotation_result():
    async def run_case():
        provider = ScriptedProvider([
            LLMResponse(
                content=(
                    '{"annotated_text":"a [[wand|魔杖]]",'
                    '"extracted_vocabulary":[{"word":"wand","translation":"魔杖","context":"a wand"}]}'
                )
            )
        ])
        service = AnnotatorService(provider)

        result = await service.annotate_text("a wand", mastered_words=["owl"], level="beginner")

        assert result.annotated_text == "a [[wand|魔杖]]"
        assert result.vocabulary[0].word == "wand"
        assert "Mastered words" in provider.messages[0][1]["content"]

    asyncio.run(run_case())


def test_annotator_service_retries_invalid_json(monkeypatch):
    async def run_case():
        provider = ScriptedProvider([
            LLMResponse(content="not json"),
            LLMResponse(content='{"annotated_text":"ok","extracted_vocabulary":[]}'),
        ])
        service = AnnotatorService(provider)

        result = await service.annotate_text("ok")

        assert result.annotated_text == "ok"
        assert len(provider.messages) == 2
        assert "previous response was not valid JSON" in provider.messages[1][1]["content"]

    monkeypatch.setenv("ANNOTATOR_JSON_RETRY", "1")
    asyncio.run(run_case())


def test_lookup_service_parses_lookup_result():
    async def run_case():
        provider = ScriptedProvider([
            LLMResponse(content='{"word":"spell","word_cn":"咒语","sentence_cn":"他念了一个咒语。"}')
        ])
        service = WordLookupService(provider)

        result = await service.lookup("spell", "He cast a spell.")

        assert result == {
            "word": "spell",
            "word_cn": "咒语",
            "sentence_cn": "他念了一个咒语。",
        }

    asyncio.run(run_case())


def test_lookup_service_raises_on_provider_error():
    async def run_case():
        provider = ScriptedProvider([LLMResponse(content="Error: nope", finish_reason="error")])
        service = WordLookupService(provider)

        with pytest.raises(RuntimeError):
            await service.lookup("spell", "He cast a spell.")

    asyncio.run(run_case())