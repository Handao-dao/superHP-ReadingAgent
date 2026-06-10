"""Chapter annotation service backed by the provider abstraction."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass

from superhp_agent.prompts import (
    BASE_ANNOTATOR_SYSTEM_PROMPT,
    build_annotator_user_prompt,
)
from superhp_agent.providers.base import LLMProvider
from superhp_agent.utils import extract_json


@dataclass(frozen=True)
class VocabItem:
    word: str
    translation: str
    context: str


@dataclass(frozen=True)
class AnnotationResult:
    annotated_text: str
    vocabulary: list[VocabItem]


class AnnotatorService:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def _json_retry_count(self) -> int:
        try:
            return max(0, int(os.getenv("ANNOTATOR_JSON_RETRY", "1")))
        except ValueError:
            return 1

    async def annotate_text(
        self,
        text: str,
        *,
        mastered_words: list[str] | None = None,
        level: str = "intermediate",
    ) -> AnnotationResult:
        user_prompt = build_annotator_user_prompt(
            text=text,
            mastered_words=mastered_words,
            level=level,
        )
        last_error: Exception | None = None

        for attempt in range(self._json_retry_count() + 1):
            prompt = user_prompt
            if attempt > 0:
                prompt += (
                    "\n\nYour previous response was not valid JSON. "
                    "Return the same task result again as valid JSON only."
                )

            response = await self.provider.chat_with_retry(
                messages=[
                    {"role": "system", "content": BASE_ANNOTATOR_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ]
            )
            if response.is_error:
                raise RuntimeError(response.content or "LLM annotation request failed")
            if not response.content:
                last_error = ValueError("LLM returned empty annotation response")
                continue

            try:
                payload = extract_json(response.content)
                return self._parse_payload(payload, fallback_text=text)
            except ValueError as exc:
                last_error = exc

        raise last_error or ValueError("LLM did not return valid JSON")

    @staticmethod
    def _parse_payload(payload: dict, *, fallback_text: str) -> AnnotationResult:
        vocab_items = []
        for item in payload.get("extracted_vocabulary", []):
            if not isinstance(item, dict):
                continue
            vocab_items.append(
                VocabItem(
                    word=str(item.get("word") or ""),
                    translation=str(item.get("translation") or ""),
                    context=str(item.get("context") or ""),
                )
            )
        return AnnotationResult(
            annotated_text=str(payload.get("annotated_text") or fallback_text),
            vocabulary=vocab_items,
        )


class LazyAnnotatorService:
    """Build the real annotator only when an annotation action is executed."""

    def __init__(self, provider_factory: Callable[[], LLMProvider]):
        self.provider_factory = provider_factory
        self._service: AnnotatorService | None = None

    def _get_service(self) -> AnnotatorService:
        if self._service is None:
            self._service = AnnotatorService(self.provider_factory())
        return self._service

    async def annotate_text(
        self,
        text: str,
        *,
        mastered_words: list[str] | None = None,
        level: str = "intermediate",
    ) -> AnnotationResult:
        return await self._get_service().annotate_text(
            text,
            mastered_words=mastered_words,
            level=level,
        )