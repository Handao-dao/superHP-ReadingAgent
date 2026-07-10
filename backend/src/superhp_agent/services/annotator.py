"""Chapter annotation service backed by the provider abstraction."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass

from superhp_agent.context import ContextBlock, ContextBundle
from superhp_agent.contracts.llm import LLMResponse
from superhp_agent.ports.events import EventSink, emit_backend_event
from superhp_agent.ports.llm import LLMProvider
from superhp_agent.profiles import (
    AnnotationItem,
    AnnotationProfile,
    EnglishNovelProfile,
    ProfileRegistry,
)

VocabItem = AnnotationItem


@dataclass(frozen=True)
class AnnotationResult:
    """Structured result consumed by storage and annotated-file rendering."""

    annotated_text: str
    vocabulary: list[AnnotationItem]


@dataclass(frozen=True)
class TextChunk:
    """One paragraph-aligned slice of a reading unit."""

    index: int
    text: str
    start_index: int
    end_index: int
    separator_before: str = ""


class AnnotationTruncatedError(RuntimeError):
    """Raised when a model stops because the output token limit was reached."""

    def __init__(self, *, chunk_index: int | None = None):
        suffix = f" for chunk {chunk_index}" if chunk_index is not None else ""
        super().__init__(f"Annotation output was truncated{suffix}.")
        self.chunk_index = chunk_index


class AnnotationChunker:
    """Split English and Chinese text with a hard language-aware size limit."""

    _UNIT_RE = re.compile(
        r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]"
        r"|[A-Za-z0-9]+(?:[’'-][A-Za-z0-9]+)*"
    )
    _SENTENCE_END_RE = re.compile(r"[.!?。！？；;]+")

    def __init__(self, *, max_chunk_words: int = 1000):
        self.max_chunk_words = max(1, int(max_chunk_words))

    def split(self, text: str) -> list[TextChunk]:
        clean_text = text.strip()
        if not clean_text:
            return []

        paragraphs = self._paragraph_spans(clean_text)
        segments: list[tuple[str, int, int, str]] = []
        previous_end = 0
        for paragraph, start, end in paragraphs:
            separator = clean_text[previous_end:start]
            fragments = self._split_oversized_paragraph(paragraph, start)
            for fragment_index, (fragment, fragment_start, fragment_end) in enumerate(fragments):
                if fragment_index == 0:
                    fragment_separator = separator
                else:
                    previous_fragment_end = fragments[fragment_index - 1][2]
                    fragment_separator = clean_text[previous_fragment_end:fragment_start]
                segments.append(
                    (fragment, fragment_start, fragment_end, fragment_separator)
                )
            previous_end = end

        chunks: list[TextChunk] = []
        current_parts: list[tuple[str, int, int, str]] = []
        current_size = 0

        for segment in segments:
            segment_size = self._measure(segment[0])
            if current_parts and current_size + segment_size > self.max_chunk_words:
                chunks.append(self._make_chunk(len(chunks) + 1, current_parts))
                current_parts = []
                current_size = 0
            current_parts.append(segment)
            current_size += segment_size

        if current_parts:
            chunks.append(self._make_chunk(len(chunks) + 1, current_parts))
        return chunks

    @classmethod
    def _measure(cls, text: str) -> int:
        """Count English words and individual CJK characters as size units."""
        return len(cls._UNIT_RE.findall(text))

    def _split_oversized_paragraph(
        self,
        paragraph: str,
        absolute_start: int,
    ) -> list[tuple[str, int, int]]:
        """Split one paragraph at sentence ends, then at hard unit boundaries."""
        unit_spans = [match.span() for match in self._UNIT_RE.finditer(paragraph)]
        if len(unit_spans) <= self.max_chunk_words:
            return [(paragraph, absolute_start, absolute_start + len(paragraph))]

        fragments: list[tuple[str, int, int]] = []
        unit_index = 0
        cursor = 0
        while unit_index < len(unit_spans):
            limit_index = min(unit_index + self.max_chunk_words, len(unit_spans))
            if limit_index == len(unit_spans):
                cutoff = len(paragraph)
            else:
                hard_cutoff = unit_spans[limit_index - 1][1]
                preferred_start = unit_spans[
                    unit_index + max(0, self.max_chunk_words // 2 - 1)
                ][0]
                sentence_ends = [
                    match.end()
                    for match in self._SENTENCE_END_RE.finditer(
                        paragraph,
                        preferred_start,
                        hard_cutoff,
                    )
                ]
                cutoff = sentence_ends[-1] if sentence_ends else hard_cutoff
                cutoff = self._include_trailing_punctuation(paragraph, cutoff)

            raw_fragment = paragraph[cursor:cutoff]
            leading = len(raw_fragment) - len(raw_fragment.lstrip())
            trailing = len(raw_fragment.rstrip())
            fragment_start = cursor + leading
            fragment_end = cursor + trailing
            if fragment_start < fragment_end:
                fragments.append(
                    (
                        paragraph[fragment_start:fragment_end],
                        absolute_start + fragment_start,
                        absolute_start + fragment_end,
                    )
                )

            cursor = cutoff
            while unit_index < len(unit_spans) and unit_spans[unit_index][1] <= cutoff:
                unit_index += 1

        return fragments

    @classmethod
    def _include_trailing_punctuation(cls, text: str, cutoff: int) -> int:
        """Keep punctuation after the last allowed unit with that fragment."""
        next_unit = cls._UNIT_RE.search(text, cutoff)
        boundary = next_unit.start() if next_unit else len(text)
        return boundary if text[cutoff:boundary].strip() else cutoff

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
    def _make_chunk(
        index: int,
        parts: list[tuple[str, int, int, str]],
    ) -> TextChunk:
        text = parts[0][0]
        for part in parts[1:]:
            text += part[3] + part[0]
        return TextChunk(
            index=index,
            text=text,
            start_index=parts[0][1],
            end_index=parts[-1][2],
            separator_before=parts[0][3],
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
        profile: AnnotationProfile | None = None,
        chunker: AnnotationChunker | None = None,
        max_concurrency: int = 8,
    ):
        self.provider = provider
        self.profile = profile or EnglishNovelProfile()
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
        profile_id: str | None = None,
    ) -> AnnotationResult:
        chunks = self.chunker.split(text)
        if not chunks:
            raise ValueError("模型没有返回译注文本。")
        normalized_level = self.profile.normalize_level(level)
        base_context = self.profile.build_annotator_base_context(
            mastered_words=mastered_words,
            level=normalized_level,
        )

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
            vocabulary=self.profile.parse_annotation_items(annotated_text),
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

        merged: list[str] = []
        chunks_by_index = {chunk.index: chunk for chunk in chunks}
        for index in sorted(results):
            annotated = results[index].strip()
            if not annotated:
                continue
            if merged:
                merged.append(chunks_by_index[index].separator_before)
            merged.append(annotated)
        return "".join(merged)

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

    def _text_from_response(self, response: LLMResponse, *, chunk_index: int | None = None) -> str:
        if response.is_error:
            raise RuntimeError(response.content or "LLM annotation request failed")
        if response.finish_reason == "length":
            raise AnnotationTruncatedError(chunk_index=chunk_index)
        if not response.content:
            raise ValueError("模型没有返回译注文本。")

        annotated_text = self.profile.normalize_annotated_text(response.content)
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


class LazyAnnotatorService:
    """Build the real annotator only when an annotation action is executed."""

    def __init__(
        self,
        provider_factory: Callable[[], LLMProvider],
        *,
        profile: AnnotationProfile | None = None,
        profile_registry: ProfileRegistry | None = None,
        max_chunk_words: int = 1000,
        max_concurrency: int = 8,
    ):
        self.provider_factory = provider_factory
        self.profile = profile or EnglishNovelProfile()
        self.profile_registry = profile_registry
        self.max_chunk_words = max_chunk_words
        self.max_concurrency = max_concurrency
        self._services: dict[str, AnnotatorService] = {}

    def _get_service(self, profile_id: str | None = None) -> AnnotatorService:
        profile = self.profile_registry.get(profile_id) if self.profile_registry is not None else self.profile
        if profile.id not in self._services:
            self._services[profile.id] = AnnotatorService(
                self.provider_factory(),
                profile=profile,
                chunker=AnnotationChunker(max_chunk_words=self.max_chunk_words),
                max_concurrency=self.max_concurrency,
            )
        return self._services[profile.id]

    async def annotate_text(
        self,
        text: str,
        *,
        mastered_words: list[str] | None = None,
        level: str = "intermediate",
        event_sink: EventSink | None = None,
        request_id: str | None = None,
        profile_id: str | None = None,
    ) -> AnnotationResult:
        return await self._get_service(profile_id).annotate_text(
            text,
            mastered_words=mastered_words,
            level=level,
            event_sink=event_sink,
            request_id=request_id,
            profile_id=profile_id,
        )
