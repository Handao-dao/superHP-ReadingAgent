"""Contextual word lookup service backed by the provider abstraction."""

from __future__ import annotations

import os

from superhp_agent.prompts import LOOKUP_SYSTEM_PROMPT, build_lookup_user_prompt
from superhp_agent.providers.base import LLMProvider
from superhp_agent.utils import extract_json


class WordLookupService:
    """Explain a selected word in sentence context.

    Lookup is modeled as an optional plugin-style service: the guided reading
    router does not need it to decide the next card.
    """
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def _json_retry_count(self) -> int:
        try:
            return max(0, int(os.getenv("LOOKUP_JSON_RETRY", "1")))
        except ValueError:
            return 1

    async def lookup(self, word: str, sentence: str) -> dict:
        """Return a compact JSON-compatible explanation for the frontend."""
        user_prompt = build_lookup_user_prompt(word=word, sentence=sentence)
        last_error: Exception | None = None

        for attempt in range(self._json_retry_count() + 1):
            prompt = user_prompt
            if attempt > 0:
                prompt += (
                    "\n\nYour previous response was not valid JSON. "
                    "Return the lookup result again as valid JSON only."
                )

            response = await self.provider.chat_with_retry(
                messages=[
                    {"role": "system", "content": LOOKUP_SYSTEM_PROMPT},
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
                return {
                    "word": str(payload.get("word") or word),
                    "word_cn": str(payload.get("word_cn") or ""),
                    "sentence_cn": str(payload.get("sentence_cn") or ""),
                }
            except ValueError as exc:
                last_error = exc

        raise last_error or ValueError("LLM did not return valid JSON")