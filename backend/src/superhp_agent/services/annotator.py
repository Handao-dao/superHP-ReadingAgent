"""Chapter annotation service backed by the provider abstraction."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass

from superhp_agent.context import ContextBlock, ContextBundle
from superhp_agent.prompts import (
    build_annotator_base_context,
)
from superhp_agent.providers.base import LLMProvider, LLMResponse
from superhp_agent.runtime.events import EventSink, emit_backend_event


@dataclass(frozen=True)
class VocabItem:
    """One vocabulary item extracted while annotating a reading unit."""

    word: str
    translation: str
    context: str
    pos: str = "other"


@dataclass(frozen=True)
class AnnotationResult:
    """Structured result consumed by storage and annotated-file rendering."""

    annotated_text: str
    vocabulary: list[VocabItem]


@dataclass(frozen=True)
class TextChunk:
    """One paragraph-aligned slice of a reading unit."""

    index: int
    text: str
    start_index: int
    end_index: int


class AnnotationTruncatedError(RuntimeError):
    """Raised when a model stops because the output token limit was reached."""

    def __init__(self, *, chunk_index: int | None = None):
        suffix = f" for chunk {chunk_index}" if chunk_index is not None else ""
        super().__init__(f"Annotation output was truncated{suffix}.")
        self.chunk_index = chunk_index


class AnnotationChunker:
    """Split long reading text on paragraph boundaries before annotation."""

    def __init__(self, *, max_chunk_words: int = 1000):
        self.max_chunk_words = max(1, int(max_chunk_words))

    def split(self, text: str) -> list[TextChunk]:
        clean_text = text.strip()
        if not clean_text:
            return []

        paragraphs = self._paragraph_spans(clean_text)
        chunks: list[TextChunk] = []
        current_parts: list[tuple[str, int, int]] = []
        current_words = 0

        for paragraph, start, end in paragraphs:
            current_parts.append((paragraph, start, end))
            current_words += len(paragraph.split())

            # max_chunk_words is a soft threshold: keep appending complete
            # paragraphs until the chunk reaches or crosses it, then seal the
            # chunk. This avoids tiny chunks while preserving paragraph shape.
            if current_words >= self.max_chunk_words:
                chunks.append(self._make_chunk(len(chunks) + 1, current_parts))
                current_parts = []
                current_words = 0

        if current_parts:
            chunks.append(self._make_chunk(len(chunks) + 1, current_parts))
        return chunks

    @staticmethod
    def _paragraph_spans(text: str) -> list[tuple[str, int, int]]:
        spans: list[tuple[str, int, int]] = []
        for match in re.finditer(r"\S(?:.*?\S)?(?=\n\s*\n|\Z)", text, flags=re.S):
            paragraph = match.group(0).strip()
            if not paragraph:
                continue
            leading_offset = len(match.group(0)) - len(match.group(0).lstrip())
            start = match.start() + leading_offset
            end = start + len(paragraph)
            spans.append((paragraph, start, end))
        return spans

    @staticmethod
    def _make_chunk(index: int, parts: list[tuple[str, int, int]]) -> TextChunk:
        return TextChunk(
            index=index,
            text="\n\n".join(part[0] for part in parts),
            start_index=parts[0][1],
            end_index=parts[-1][2],
        )


class AnnotatorService:
    """Generate annotated text and derive vocabulary from inline markers.

    The model is asked to return annotated passage text only. Long inputs are
    split into paragraph-aligned chunks, processed concurrently, and merged on
    the backend before any annotated copy is saved.
    """

    def __init__(
        self,
        provider: LLMProvider,
        *,
        chunker: AnnotationChunker | None = None,
        max_concurrency: int = 100,
    ):
        self.provider = provider
        self.chunker = chunker or AnnotationChunker()
        self.max_concurrency = max(1, int(max_concurrency))

    async def annotate_text(
        self,
        text: str,
        *,
        mastered_words: list[str] | None = None,
        level: str = "intermediate",
        event_sink: EventSink | None = None,
        request_id: str | None = None,
    ) -> AnnotationResult:
        chunks = self.chunker.split(text)
        if not chunks:
            raise ValueError("模型没有返回译注文本。")
        base_context = build_annotator_base_context(mastered_words=mastered_words, level=level)

        if len(chunks) == 1:
            annotated_text = await self._annotate_chunk(
                chunks[0],
                base_context=base_context,
                event_sink=event_sink,
                request_id=request_id,
            )
        else:
            annotated_text = await self._annotate_chunks(
                chunks,
                base_context=base_context,
                event_sink=event_sink,
                request_id=request_id,
            )

        if not annotated_text:
            raise ValueError("模型没有返回译注文本。")

        return AnnotationResult(
            annotated_text=annotated_text,
            vocabulary=self._vocabulary_from_annotation(annotated_text),
        )

    async def _annotate_chunks(
        self,
        chunks: list[TextChunk],
        *,
        base_context: ContextBundle,
        event_sink: EventSink | None,
        request_id: str | None,
    ) -> str:
        total = len(chunks)
        await self._emit_progress(
            event_sink,
            request_id=request_id,
            current=0,
            total=total,
            stage="chunking",
            message=f"Annotating section 0 of {total}...",
        )

        semaphore = asyncio.Semaphore(self.max_concurrency)
        results: dict[int, str] = {}
        completed = 0

        async def run_chunk(chunk: TextChunk) -> tuple[int, str]:
            async with semaphore:
                return chunk.index, await self._annotate_chunk(
                    chunk,
                    base_context=base_context,
                    event_sink=event_sink,
                    request_id=request_id,
                )

        tasks = [asyncio.create_task(run_chunk(chunk)) for chunk in chunks]
        try:
            for task in asyncio.as_completed(tasks):
                index, annotated = await task
                results[index] = annotated
                completed += 1
                await self._emit_progress(
                    event_sink,
                    request_id=request_id,
                    current=completed,
                    total=total,
                    stage="chunk",
                    message=f"Annotating section {completed} of {total}...",
                )
        except Exception:
            for task in tasks:
                task.cancel()
            raise

        return "\n\n".join(results[index].strip() for index in sorted(results) if results[index].strip())

    async def _annotate_chunk(
        self,
        chunk: TextChunk,
        *,
        base_context: ContextBundle,
        event_sink: EventSink | None,
        request_id: str | None,
    ) -> str:
        context = base_context.with_blocks(self._reader_text_block(chunk.text))
        response = await self.provider.chat_with_retry(
            messages=context.to_messages(),
            on_retry_wait=(
                self._retry_event_sink(event_sink, request_id=request_id)
                if event_sink is not None
                else None
            ),
        )
        return self._text_from_response(response, chunk_index=chunk.index)

    @staticmethod
    def _reader_text_block(text: str) -> ContextBlock:
        return ContextBlock("reader_text", text, role="user")

    @staticmethod
    def _text_from_response(response: LLMResponse, *, chunk_index: int | None = None) -> str:
        if response.is_error:
            raise RuntimeError(response.content or "LLM annotation request failed")
        if response.finish_reason == "length":
            raise AnnotationTruncatedError(chunk_index=chunk_index)
        if not response.content:
            raise ValueError("模型没有返回译注文本。")

        annotated_text = AnnotatorService._normalize_annotated_text(response.content)
        if not annotated_text:
            raise ValueError("模型没有返回译注文本。")
        return annotated_text

    @staticmethod
    async def _emit_progress(
        event_sink: EventSink | None,
        *,
        request_id: str | None,
        current: int,
        total: int,
        stage: str,
        message: str,
    ) -> None:
        if event_sink is None:
            return
        await emit_backend_event(
            event_sink,
            "annotation.progress",
            request_id=request_id,
            current=current,
            total=total,
            stage=stage,
            message=message,
        )

    @staticmethod
    def _retry_event_sink(event_sink: EventSink, *, request_id: str | None):
        async def on_retry_wait(message: str) -> None:
            await emit_backend_event(
                event_sink,
                "annotation.model_retry",
                request_id=request_id,
                message=message,
            )

        return on_retry_wait

    @classmethod
    def _normalize_annotated_text(cls, content: str) -> str:
        text = _strip_code_fence(content).strip()
        legacy_json_text = _extract_loose_annotated_text(text)
        if legacy_json_text is not None:
            text = legacy_json_text.strip()
        return text

    @staticmethod
    def _vocabulary_from_annotation(text: str) -> list[VocabItem]:
        seen: set[str] = set()
        items: list[VocabItem] = []
        for match in re.finditer(r"\[\[([^|\]]+)\|([^|\]]+)(?:\|([^|\]]+))?\]\]", text):
            word = match.group(1).strip()
            translation = match.group(2).strip()
            pos = _normalize_marker_pos(match.group(3))
            key = word.lower()
            if not word or not translation or key in seen:
                continue
            seen.add(key)
            items.append(
                VocabItem(
                    word=word,
                    translation=translation,
                    context=_annotation_context(text, match.start()),
                    pos=pos,
                )
            )
        return items


class LazyAnnotatorService:
    """Build the real annotator only when an annotation action is executed."""

    def __init__(
        self,
        provider_factory: Callable[[], LLMProvider],
        *,
        max_chunk_words: int = 1000,
        max_concurrency: int = 100,
    ):
        self.provider_factory = provider_factory
        self.max_chunk_words = max_chunk_words
        self.max_concurrency = max_concurrency
        self._service: AnnotatorService | None = None

    def _get_service(self) -> AnnotatorService:
        if self._service is None:
            self._service = AnnotatorService(
                self.provider_factory(),
                chunker=AnnotationChunker(max_chunk_words=self.max_chunk_words),
                max_concurrency=self.max_concurrency,
            )
        return self._service

    async def annotate_text(
        self,
        text: str,
        *,
        mastered_words: list[str] | None = None,
        level: str = "intermediate",
        event_sink: EventSink | None = None,
        request_id: str | None = None,
    ) -> AnnotationResult:
        return await self._get_service().annotate_text(
            text,
            mastered_words=mastered_words,
            level=level,
            event_sink=event_sink,
            request_id=request_id,
        )


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) >= 2 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return stripped


def _extract_loose_annotated_text(text: str) -> str | None:
    marker = '"annotated_text"'
    start = text.find(marker)
    if start < 0:
        return None
    colon = text.find(":", start + len(marker))
    if colon < 0:
        return None
    value = text[colon + 1 :].lstrip()
    if value.startswith('"'):
        value = value[1:]

    vocab_marker = re.search(r'"\s*,\s*"extracted_vocabulary"\s*:', value)
    if vocab_marker:
        value = value[: vocab_marker.start()]
    else:
        value = re.sub(r'"\s*}\s*$', "", value, flags=re.DOTALL)
        value = re.sub(r'"\s*,\s*}\s*$', "", value, flags=re.DOTALL)

    value = value.strip()
    if not value:
        return None
    return value.replace("\\n", "\n").replace('\\"', '"')


def _annotation_context(text: str, index: int) -> str:
    left = max(text.rfind(".", 0, index), text.rfind("!", 0, index), text.rfind("?", 0, index))
    right_candidates = [pos for pos in (text.find(".", index), text.find("!", index), text.find("?", index)) if pos >= 0]
    right = min(right_candidates) if right_candidates else min(len(text), index + 120)
    start = left + 1 if left >= 0 else max(0, index - 60)
    return re.sub(r"\s+", " ", text[start : right + 1]).strip()[:240]


def _normalize_marker_pos(pos: str | None) -> str:
    value = str(pos or "").strip().lower()
    aliases = {
        "n": "noun",
        "v": "verb",
        "adj": "adjective",
        "adv": "adverb",
    }
    value = aliases.get(value, value)
    return value if value in {"noun", "verb", "adjective", "adverb", "phrase", "other"} else "other"
