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
    """One group of complete paragraphs sent to the annotation model."""

    index: int
    text: str


class AnnotationTruncatedError(RuntimeError):
    """Raised when a model stops because the output token limit was reached."""

    def __init__(self, *, chunk_index: int | None = None):
        suffix = f" for chunk {chunk_index}" if chunk_index is not None else ""
        super().__init__(f"Annotation output was truncated{suffix}.")
        self.chunk_index = chunk_index


class AnnotationChunker:
    """Estimate paragraph sizes and pack complete paragraphs for annotation."""

    # This is a rough sizing rule, not a model tokenizer: count each English
    # word, CJK character, or remaining non-whitespace symbol as one unit.
    _UNIT_RE = re.compile(
        r"[A-Za-z0-9]+(?:[’'-][A-Za-z0-9]+)*"
        r"|[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]"
        r"|[^\s]"
    )

    def __init__(self, *, max_chunk_words: int = 1500):
        self.max_chunk_words = max(1, int(max_chunk_words))

    def split(self, text: str) -> list[TextChunk]:
        clean_text = text.strip()
        if not clean_text:
            return []

        paragraphs = self._paragraphs(clean_text)
        chunks: list[TextChunk] = []
        current_paragraphs: list[str] = []
        current_size = 0

        for paragraph in paragraphs:
            paragraph_size = self._measure(paragraph)
            if paragraph_size > self.max_chunk_words:
                raise ValueError(
                    "A paragraph exceeds the annotation input limit "
                    f"({paragraph_size} > {self.max_chunk_words})."
                )
            if (
                current_paragraphs
                and current_size + paragraph_size > self.max_chunk_words
            ):
                chunks.append(self._make_chunk(len(chunks) + 1, current_paragraphs))
                current_paragraphs = []
                current_size = 0
            current_paragraphs.append(paragraph)
            current_size += paragraph_size

        if current_paragraphs:
            chunks.append(self._make_chunk(len(chunks) + 1, current_paragraphs))
        return chunks

    @classmethod
    def _measure(cls, text: str) -> int:
        """Count English words, CJK characters, and punctuation as rough units."""
        return len(cls._UNIT_RE.findall(text))

    @staticmethod
    def _paragraphs(text: str) -> list[str]:
        """Use blank lines as the only structural splitting rule."""
        return [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]

    @staticmethod
    def _make_chunk(index: int, paragraphs: list[str]) -> TextChunk:
        return TextChunk(index=index, text="\n\n".join(paragraphs))


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
        finally:
            # Never leave model requests running after this annotation call
            # succeeds, fails, or is cancelled by its caller.
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        return "\n\n".join(
            results[index].strip()
            for index in sorted(results)
            if results[index].strip()
        )

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
        max_chunk_words: int = 1500,
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
