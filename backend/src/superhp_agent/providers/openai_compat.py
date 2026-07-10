"""OpenAI-compatible provider implementation."""

from __future__ import annotations

import asyncio
from typing import Any

from superhp_agent.contracts.llm import LLMResponse
from superhp_agent.providers.base import BaseLLMProvider
from superhp_agent.providers.registry import ProviderSpec

AsyncOpenAI: Any = None


_THINKING_STYLE_MAP = {
    "thinking_type": lambda enabled: {"thinking": {"type": "enabled" if enabled else "disabled"}},
}


class OpenAICompatProvider(BaseLLMProvider):
    """Adapter for vendors that expose an OpenAI-compatible chat API."""
    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_base: str | None = None,
        default_model: str,
        timeout: float = 60,
        spec: ProviderSpec | None = None,
    ):
        super().__init__(api_key, api_base)
        self.default_model = default_model
        self.timeout = timeout
        self.spec = spec
        self._client = None
        self._client_lock = asyncio.Lock()

    def get_default_model(self) -> str:
        return self.default_model

    async def _ensure_client(self):
        """Import and construct the SDK client lazily on first model call."""
        if self._client is not None:
            return self._client
        async with self._client_lock:
            if self._client is not None:
                return self._client
            global AsyncOpenAI
            if AsyncOpenAI is None:
                from openai import AsyncOpenAI as _AsyncOpenAI

                AsyncOpenAI = _AsyncOpenAI
            self._client = AsyncOpenAI(
                api_key=self.api_key or "no-key",
                base_url=self.api_base or None,
                timeout=self.timeout,
                max_retries=0,
            )
            return self._client

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
        client = await self._ensure_client()
        try:
            kwargs = self._build_kwargs(
                messages=messages,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                reasoning_effort=reasoning_effort,
                extra_body=extra_body,
            )
            response = await client.chat.completions.create(**kwargs)
            return self._parse(response)
        except Exception as exc:
            return self._handle_error(exc)

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.2,
        reasoning_effort: str | None = None,
        extra_body: dict[str, Any] | None = None,
        on_content_delta=None,
    ) -> LLMResponse:
        client = await self._ensure_client()
        try:
            kwargs = self._build_kwargs(
                messages=messages,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                reasoning_effort=reasoning_effort,
                extra_body=extra_body,
            )
            kwargs["stream"] = True
            kwargs["stream_options"] = {"include_usage": True}
            chunks = []
            stream = await client.chat.completions.create(**kwargs)
            async for chunk in stream:
                chunks.append(chunk)
                if on_content_delta:
                    text = self._extract_chunk_delta_text(chunk)
                    if text:
                        await on_content_delta(text)
            return self._parse_chunks(chunks)
        except Exception as exc:
            return self._handle_error(exc)

    def _build_kwargs(
        self,
        *,
        messages: list[dict[str, Any]],
        model: str | None,
        max_tokens: int,
        temperature: float,
        reasoning_effort: str | None,
        extra_body: dict[str, Any] | None,
    ) -> dict[str, Any]:
        # extra_body carries provider-specific extensions such as thinking flags
        # while the public provider API stays small and stable.
        body = dict(extra_body or {})
        thinking_body = self._thinking_extra_body(reasoning_effort)
        if thinking_body:
            body = self._deep_merge(thinking_body, body)

        kwargs: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": self._sanitize_messages(messages),
            "max_tokens": max(1, int(max_tokens)),
            "temperature": temperature,
        }
        if body:
            kwargs["extra_body"] = body
        return kwargs

    def _thinking_extra_body(self, reasoning_effort: str | None) -> dict[str, Any] | None:
        style = self.spec.thinking_style if self.spec else ""
        builder = _THINKING_STYLE_MAP.get(style)
        if not builder:
            return None
        # DeepSeek-style APIs accept an explicit disabled flag. SuperHP's
        # annotation tasks default to fast, non-thinking responses.
        enabled = bool(reasoning_effort and reasoning_effort.lower() != "none")
        return builder(enabled)

    @staticmethod
    def _sanitize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        allowed = {"role", "content", "name", "tool_call_id", "tool_calls"}
        result = []
        for message in messages:
            clean = {key: value for key, value in message.items() if key in allowed}
            if clean.get("role") == "assistant" and "content" not in clean:
                clean["content"] = None
            result.append(clean)
        return result

    @staticmethod
    def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        merged = dict(base)
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = OpenAICompatProvider._deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged

    @classmethod
    def _parse(cls, response: Any) -> LLMResponse:
        if isinstance(response, str):
            return LLMResponse(content=response)
        if isinstance(response, dict):
            choices = response.get("choices") or []
            if not choices:
                return LLMResponse(content="Error: LLM response had empty choices", finish_reason="error")
            choice = choices[0]
            message = choice.get("message") or {}
            content = message.get("content")
            reasoning = message.get("reasoning_content") or message.get("reasoning")
            return LLMResponse(
                content=content,
                finish_reason=choice.get("finish_reason") or "stop",
                usage=cls._extract_usage(response),
                reasoning_content=reasoning,
            )

        choices = getattr(response, "choices", None) or []
        if not choices:
            return LLMResponse(content="Error: LLM response had empty choices", finish_reason="error")
        choice = choices[0]
        message = getattr(choice, "message", None)
        content = getattr(message, "content", None) if message is not None else None
        reasoning = None
        if message is not None:
            reasoning = getattr(message, "reasoning_content", None) or getattr(message, "reasoning", None)
        return LLMResponse(
            content=content,
            finish_reason=getattr(choice, "finish_reason", None) or "stop",
            usage=cls._extract_usage(response),
            reasoning_content=reasoning,
        )

    @classmethod
    def _parse_chunks(cls, chunks: list[Any]) -> LLMResponse:
        parts: list[str] = []
        usage: dict[str, int] = {}
        finish_reason = "stop"
        for chunk in chunks:
            text = cls._extract_chunk_delta_text(chunk)
            if text:
                parts.append(text)
            chunk_finish = cls._extract_chunk_finish_reason(chunk)
            if chunk_finish:
                finish_reason = chunk_finish
            usage = cls._extract_usage(chunk) or usage
        return LLMResponse(content="".join(parts) or None, finish_reason=finish_reason, usage=usage)

    @staticmethod
    def _extract_chunk_delta_text(chunk: Any) -> str:
        if isinstance(chunk, str):
            return chunk
        if isinstance(chunk, dict):
            choices = chunk.get("choices") or []
            if not choices:
                return ""
            delta = choices[0].get("delta") or {}
            return delta.get("content") or ""
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            return ""
        delta = getattr(choices[0], "delta", None)
        return getattr(delta, "content", None) or ""

    @staticmethod
    def _extract_chunk_finish_reason(chunk: Any) -> str | None:
        if isinstance(chunk, dict):
            choices = chunk.get("choices") or []
            return (choices[0].get("finish_reason") if choices else None) or None
        choices = getattr(chunk, "choices", None) or []
        return getattr(choices[0], "finish_reason", None) if choices else None

    @staticmethod
    def _extract_usage(payload: Any) -> dict[str, int]:
        usage = payload.get("usage") if isinstance(payload, dict) else getattr(payload, "usage", None)
        if not usage:
            return {}
        if isinstance(usage, dict):
            return {key: int(value) for key, value in usage.items() if isinstance(value, int)}
        result = {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = getattr(usage, key, None)
            if isinstance(value, int):
                result[key] = value
        return result

    def _handle_error(self, exc: Exception) -> LLMResponse:
        """Normalize SDK exceptions into retry-aware LLMResponse objects."""
        response = getattr(exc, "response", None)
        status_code = getattr(exc, "status_code", None)
        if status_code is None and response is not None:
            status_code = getattr(response, "status_code", None)
        headers = getattr(response, "headers", None)
        body = getattr(exc, "body", None) or getattr(response, "text", None)
        body_text = body if isinstance(body, str) else str(body) if body is not None else ""
        content = f"Error: {body_text.strip()[:500]}" if body_text.strip() else f"Error calling LLM: {exc}"
        return LLMResponse(
            content=content,
            finish_reason="error",
            error_status_code=int(status_code) if status_code is not None else None,
            error_kind=self._error_kind(exc),
            error_retry_after_s=BaseLLMProvider.extract_retry_after_from_headers(headers),
        )

    @staticmethod
    def _error_kind(exc: Exception) -> str | None:
        name = exc.__class__.__name__.lower()
        if "timeout" in name:
            return "timeout"
        if "connection" in name:
            return "connection"
        return None
