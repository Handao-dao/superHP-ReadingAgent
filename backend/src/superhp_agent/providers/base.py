"""Base LLM provider contract.

This is intentionally smaller than nanobot's production provider layer, but it
keeps the same core idea: application services depend on LLMProvider and
LLMResponse, not on any vendor SDK.
"""

from __future__ import annotations

import asyncio
import re
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from typing import Any


@dataclass(frozen=True)
class GenerationSettings:
    temperature: float = 0.2
    max_tokens: int = 4096
    reasoning_effort: str | None = None


@dataclass
class LLMResponse:
    content: str | None
    finish_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict)
    reasoning_content: str | None = None
    retry_after: float | None = None
    error_status_code: int | None = None
    error_kind: str | None = None
    error_type: str | None = None
    error_code: str | None = None
    error_retry_after_s: float | None = None
    error_should_retry: bool | None = None

    @property
    def is_error(self) -> bool:
        return self.finish_reason == "error"


class LLMProvider(ABC):
    _SENTINEL = object()
    _RETRY_DELAYS = (1.0, 2.0, 4.0)
    _RETRYABLE_STATUS_CODES = frozenset({408, 409, 429})
    _TRANSIENT_ERROR_KINDS = frozenset({"timeout", "connection"})
    _TRANSIENT_ERROR_MARKERS = (
        "429",
        "rate limit",
        "too many requests",
        "500",
        "502",
        "503",
        "504",
        "overloaded",
        "timeout",
        "timed out",
        "connection",
        "server error",
        "temporarily unavailable",
        "速率限制",
    )
    _NON_RETRYABLE_429_TOKENS = frozenset({
        "insufficient_quota",
        "quota_exceeded",
        "quota_exhausted",
        "billing_hard_limit_reached",
        "insufficient_balance",
        "payment_required",
    })

    def __init__(self, api_key: str | None = None, api_base: str | None = None):
        self.api_key = api_key
        self.api_base = api_base
        self.generation = GenerationSettings()

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.2,
        reasoning_effort: str | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> LLMResponse:
        raise NotImplementedError

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.2,
        reasoning_effort: str | None = None,
        extra_body: dict[str, Any] | None = None,
        on_content_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> LLMResponse:
        response = await self.chat(
            messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            extra_body=extra_body,
        )
        if on_content_delta and response.content:
            await on_content_delta(response.content)
        return response

    @abstractmethod
    def get_default_model(self) -> str:
        raise NotImplementedError

    async def chat_with_retry(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        max_tokens: object = _SENTINEL,
        temperature: object = _SENTINEL,
        reasoning_effort: object = _SENTINEL,
        extra_body: dict[str, Any] | None = None,
        on_retry_wait: Callable[[str], Awaitable[None]] | None = None,
    ) -> LLMResponse:
        if max_tokens is self._SENTINEL or max_tokens is None:
            max_tokens = self.generation.max_tokens
        if temperature is self._SENTINEL or temperature is None:
            temperature = self.generation.temperature
        if reasoning_effort is self._SENTINEL:
            reasoning_effort = self.generation.reasoning_effort

        return await self._run_with_retry(
            self.chat,
            dict(
                messages=messages,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                reasoning_effort=reasoning_effort,
                extra_body=extra_body,
            ),
            on_retry_wait=on_retry_wait,
        )

    async def chat_stream_with_retry(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        max_tokens: object = _SENTINEL,
        temperature: object = _SENTINEL,
        reasoning_effort: object = _SENTINEL,
        extra_body: dict[str, Any] | None = None,
        on_content_delta: Callable[[str], Awaitable[None]] | None = None,
        on_retry_wait: Callable[[str], Awaitable[None]] | None = None,
    ) -> LLMResponse:
        if max_tokens is self._SENTINEL or max_tokens is None:
            max_tokens = self.generation.max_tokens
        if temperature is self._SENTINEL or temperature is None:
            temperature = self.generation.temperature
        if reasoning_effort is self._SENTINEL:
            reasoning_effort = self.generation.reasoning_effort

        return await self._run_with_retry(
            self.chat_stream,
            dict(
                messages=messages,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                reasoning_effort=reasoning_effort,
                extra_body=extra_body,
                on_content_delta=on_content_delta,
            ),
            on_retry_wait=on_retry_wait,
        )

    async def _run_with_retry(
        self,
        call: Callable[..., Awaitable[LLMResponse]],
        kwargs: dict[str, Any],
        *,
        on_retry_wait: Callable[[str], Awaitable[None]] | None,
    ) -> LLMResponse:
        last_response: LLMResponse | None = None
        for attempt in range(len(self._RETRY_DELAYS) + 1):
            try:
                response = await call(**kwargs)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                response = LLMResponse(
                    content=f"Error calling LLM: {exc}",
                    finish_reason="error",
                )

            if not response.is_error:
                return response
            last_response = response
            if not self._is_transient_response(response) or attempt >= len(self._RETRY_DELAYS):
                return response

            delay = self._extract_retry_after_from_response(response) or self._RETRY_DELAYS[attempt]
            if on_retry_wait:
                await on_retry_wait(
                    f"Model request failed, retrying in {max(1, int(round(delay)))}s."
                )
            await asyncio.sleep(delay)

        return last_response or LLMResponse(content="Unknown LLM error", finish_reason="error")

    @classmethod
    def _is_transient_response(cls, response: LLMResponse) -> bool:
        if response.error_should_retry is not None:
            return bool(response.error_should_retry)
        if response.error_status_code is not None:
            status = response.error_status_code
            if status == 429:
                tokens = {response.error_type or "", response.error_code or ""}
                if any(token.lower() in cls._NON_RETRYABLE_429_TOKENS for token in tokens):
                    return False
                return True
            if status in cls._RETRYABLE_STATUS_CODES or status >= 500:
                return True
        if (response.error_kind or "").lower() in cls._TRANSIENT_ERROR_KINDS:
            return True
        text = (response.content or "").lower()
        return any(marker in text for marker in cls._TRANSIENT_ERROR_MARKERS)

    @classmethod
    def _extract_retry_after_from_response(cls, response: LLMResponse) -> float | None:
        if response.error_retry_after_s and response.error_retry_after_s > 0:
            return response.error_retry_after_s
        if response.retry_after and response.retry_after > 0:
            return response.retry_after
        return cls._extract_retry_after(response.content)

    @classmethod
    def _extract_retry_after(cls, content: str | None) -> float | None:
        text = (content or "").lower()
        patterns = (
            r"retry after\s+(\d+(?:\.\d+)?)\s*(ms|milliseconds|s|sec|seconds|m|min|minutes)?",
            r"try again in\s+(\d+(?:\.\d+)?)\s*(ms|milliseconds|s|sec|seconds|m|min|minutes)",
            r"retry[_-]?after[\"'\s:=]+(\d+(?:\.\d+)?)",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                value = float(match.group(1))
                unit = match.group(2) or "s"
                return cls._to_seconds(value, unit)
        return None

    @staticmethod
    def _to_seconds(value: float, unit: str) -> float:
        unit = unit.lower()
        if unit in {"ms", "milliseconds"}:
            return max(0.1, value / 1000)
        if unit in {"m", "min", "minutes"}:
            return max(0.1, value * 60)
        return max(0.1, value)

    @classmethod
    def extract_retry_after_from_headers(cls, headers: Any) -> float | None:
        if not headers:
            return None

        def header(name: str) -> Any:
            if hasattr(headers, "get"):
                value = headers.get(name) or headers.get(name.title())
                if value is not None:
                    return value
            if isinstance(headers, dict):
                for key, value in headers.items():
                    if isinstance(key, str) and key.lower() == name.lower():
                        return value
            return None

        retry_ms = header("retry-after-ms")
        if retry_ms is not None:
            try:
                return max(0.1, float(retry_ms) / 1000)
            except (TypeError, ValueError):
                pass

        retry_after = header("retry-after")
        if retry_after is None:
            return None
        text = str(retry_after).strip()
        if re.fullmatch(r"\d+(?:\.\d+)?", text):
            return max(0.1, float(text))
        try:
            dt = parsedate_to_datetime(text)
        except Exception:
            return None
        if dt.tzinfo is None:
            return 0.1
        return max(0.1, (dt - dt.now(dt.tzinfo)).total_seconds())