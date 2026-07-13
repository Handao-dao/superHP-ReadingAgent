"""Contextual word lookup service backed by the provider abstraction."""

from __future__ import annotations

import os

from superhp_agent.domain.vocabulary import normalize_pos
from superhp_agent.ports.llm import LLMProvider
from superhp_agent.profiles import AnnotationProfile, EnglishNovelProfile
from superhp_agent.utils import extract_json


class WordLookupService:
    """Explain a selected word in sentence context.

    Lookup is modeled as an optional plugin-style service: the guided reading
    router does not need it to decide the next card.
    """
    def __init__(self, provider: LLMProvider, *, profile: AnnotationProfile | None = None):
        self.provider = provider
        self.profile = profile or EnglishNovelProfile()

    def _json_retry_count(self) -> int:
        try:
            return max(0, int(os.getenv("LOOKUP_JSON_RETRY", "1")))
        except ValueError:
            return 1

    async def lookup(self, word: str, sentence: str) -> dict:
        """Return a compact JSON-compatible explanation for the frontend."""
        user_prompt = self.profile.build_lookup_user_prompt(word=word, sentence=sentence)
        last_error: Exception | None = None

        for attempt in range(self._json_retry_count() + 1):
            prompt = user_prompt
            if attempt > 0:
                prompt += (
                    "\n\nYour previous response did not match the required JSON fields. "
                    "Return a complete lookup result as valid JSON only."
                )

            response = await self.provider.chat_with_retry(
                messages=[
                    {"role": "system", "content": self.profile.lookup_system_prompt},
                    {"role": "user", "content": prompt},
                ]
            )
            if response.is_error:
                raise RuntimeError(response.content or "LLM lookup request failed")
            if not response.content:
                last_error = ValueError("LLM returned empty lookup response")
                continue

            try:
                payload = extract_json(response.content)
                return _normalize_lookup_payload(
                    payload,
                    word=word,
                    sentence=sentence,
                )
            except ValueError as exc:
                last_error = exc

        raise last_error or ValueError("LLM did not return valid JSON")


def _normalize_lookup_payload(payload: object, *, word: str, sentence: str) -> dict:
    """Validate required model fields and preserve the user's queried word."""
    if not isinstance(payload, dict):
        raise ValueError("LLM lookup response must be a JSON object")

    word_cn = str(payload.get("word_cn") or "").strip()
    sentence_cn = str(payload.get("sentence_cn") or "").strip()
    if not word_cn:
        raise ValueError("LLM lookup response is missing word_cn")
    if sentence.strip() and not sentence_cn:
        raise ValueError("LLM lookup response is missing sentence_cn")

    return {
        "word": word,
        "word_cn": word_cn,
        "pos": normalize_pos(payload.get("pos")),
        "sentence_cn": sentence_cn,
    }
