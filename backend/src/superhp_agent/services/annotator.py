"""Orchestrate paragraph chunking, concurrent annotation, and safe fallback.

Provider owns request retry. Profile owns text-specific output validation.
This Service coordinates them, converts expected model problems into readable
original-text fallbacks, and returns structured outcomes without persisting or
making frontend flow decisions.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass

from superhp_agent.context import ContextBlock, ContextBundle
from superhp_agent.contracts.annotation import (
    AnnotationChunkOutcome,
    AnnotationResult,
    ServiceIssue,
)
from superhp_agent.ports.events import EventSink, emit_backend_event
from superhp_agent.ports.llm import LLMProvider
from superhp_agent.profiles import (
    AnnotationProfile,
    EnglishNovelProfile,
    ProfileRegistry,
)


@dataclass(frozen=True)
class TextChunk:
    """One group of complete paragraphs sent to the annotation model."""

    index: int
    text: str


class AnnotationChunker:
    """Estimate paragraph sizes and pack complete paragraphs for annotation."""

    # This is a rough sizing rule, not a model tokenizer: count each English
    # word, CJK character, or remaining non-whitespace symbol as one unit.
    _UNIT_RE = re.compile(
        r"[A-Za-z0-9]+(?:[’'-][A-Za-z0-9]+)*"
        r"|[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]"
        r"|[^\s]"
    )

    def __init__(self, *, max_chunk_words: int = 1000):
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
        event_sink: EventSink | None = None,
        request_id: str | None = None,
        profile_id: str | None = None,
        selection_policy_id: str | None = None,
    ) -> AnnotationResult:
        """Annotate a reading unit and return complete text plus degradation data."""
        chunks = self.chunker.split(text)
        if not chunks:
            raise ValueError("模型没有返回译注文本。")
        base_context = self.profile.build_annotator_base_context(
            mastered_words=mastered_words,
            selection_policy_id=selection_policy_id,
        )

        outcomes = await self._annotate_chunks(
            chunks,
            base_context=base_context,
            event_sink=event_sink,
            request_id=request_id,
        )

        annotated_text = "\n\n".join(outcome.text.strip() for outcome in outcomes)
        issues = [outcome.issue for outcome in outcomes if outcome.issue is not None]
        candidate_issues = [
            issue
            for outcome in outcomes
            for issue in outcome.candidate_issues
        ]

        return AnnotationResult(
            annotated_text=annotated_text,
            vocabulary=self.profile.parse_annotation_items(annotated_text),
            issues=issues,
            candidate_issues=candidate_issues,
            validated_chunk_count=sum(not outcome.degraded for outcome in outcomes),
            total_chunk_count=len(outcomes),
        )

    async def _annotate_chunks(
        self,
        chunks: list[TextChunk],
        *,
        base_context: ContextBundle,
        event_sink: EventSink | None,
        request_id: str | None,
    ) -> list[AnnotationChunkOutcome]:
        """Run chunks concurrently, emit progress, and restore source order."""
        total = len(chunks)
        await self._emit_progress(
            event_sink,
            request_id=request_id,
            current=0,
            total=total,
            stage="chunking",
            message=f"Preparing {total} annotation sections...",
        )

        semaphore = asyncio.Semaphore(self.max_concurrency)
        results: dict[int, AnnotationChunkOutcome] = {}
        completed = 0

        async def run_chunk(chunk: TextChunk) -> AnnotationChunkOutcome:
            async with semaphore:
                return await self._annotate_chunk(
                    chunk,
                    base_context=base_context,
                    event_sink=event_sink,
                    request_id=request_id,
                )

        tasks = [asyncio.create_task(run_chunk(chunk)) for chunk in chunks]
        try:
            for task in asyncio.as_completed(tasks):
                outcome = await task
                results[outcome.index] = outcome
                completed += 1
                if outcome.issue is not None:
                    await self._emit_degraded(
                        event_sink,
                        request_id=request_id,
                        issue=outcome.issue,
                    )
                for issue in outcome.candidate_issues:
                    await self._emit_candidate_rejected(
                        event_sink,
                        request_id=request_id,
                        issue=issue,
                    )
                await self._emit_progress(
                    event_sink,
                    request_id=request_id,
                    current=completed,
                    total=total,
                    stage="chunk",
                    message=f"Completed {completed} of {total} sections.",
                    chunk_index=outcome.index,
                )
        finally:
            # Never leave model requests running after this annotation call
            # succeeds, fails, or is cancelled by its caller.
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        return [results[index] for index in sorted(results)]

    async def _annotate_chunk(
        self,
        chunk: TextChunk,
        *,
        base_context: ContextBundle,
        event_sink: EventSink | None,
        request_id: str | None,
    ) -> AnnotationChunkOutcome:
        """Turn one Provider response into validated text or a safe fallback.

        Only expected model states become degraded outcomes. Cancellation and
        unexpected program exceptions remain exceptions so bugs are visible.
        """
        context = base_context.with_blocks(self._reader_text_block(chunk.text))
        response = await self.provider.chat_with_retry(
            messages=context.to_messages(),
            on_retry_wait=(
                self._retry_event_sink(
                    event_sink,
                    request_id=request_id,
                    chunk_index=chunk.index,
                )
                if event_sink is not None
                else None
            ),
        )
        if response.is_error:
            return self._degraded_outcome(
                chunk,
                category="provider",
                code="provider_failed",
                message="The model request failed and this section uses the original text.",
            )
        if response.finish_reason == "length":
            return self._degraded_outcome(
                chunk,
                category="validation",
                code="truncated_output",
                message="The model output was truncated and this section uses the original text.",
            )
        if not response.content:
            return self._degraded_outcome(
                chunk,
                category="validation",
                code="empty_output",
                message="The model returned no text and this section uses the original text.",
            )

        annotated_text = self.profile.normalize_annotated_text(response.content)
        projection_method = getattr(self.profile, "project_annotation_response", None)
        if callable(projection_method):
            try:
                projection = projection_method(
                    source_text=chunk.text,
                    content=response.content,
                )
            except ValueError:
                return self._degraded_outcome(
                    chunk,
                    category="validation",
                    code="malformed_candidate_output",
                    message="The model returned an invalid annotation candidate document.",
                )
            if projection is not None:
                candidate_issues = tuple(
                    ServiceIssue(
                        category="candidate",
                        code=rejection.code,
                        message="One annotation candidate could not be applied safely.",
                        chunk_index=chunk.index,
                        item_index=rejection.candidate_index,
                    )
                    for rejection in projection.rejections
                )
                return AnnotationChunkOutcome(
                    index=chunk.index,
                    text=projection.annotated_text,
                    candidate_issues=candidate_issues,
                )
        if not annotated_text:
            return self._degraded_outcome(
                chunk,
                category="validation",
                code="empty_output",
                message="The model returned no text and this section uses the original text.",
            )
        issue = self.profile.validate_annotated_text(
            source_text=chunk.text,
            annotated_text=annotated_text,
        )
        if issue is not None:
            return AnnotationChunkOutcome(
                index=chunk.index,
                text=chunk.text,
                issue=ServiceIssue(
                    category=issue.category,
                    code=issue.code,
                    message=issue.message,
                    chunk_index=chunk.index,
                ),
            )
        return AnnotationChunkOutcome(index=chunk.index, text=annotated_text)

    @staticmethod
    def _reader_text_block(text: str) -> ContextBlock:
        return ContextBlock("reader_text", text, role="user")

    @staticmethod
    def _degraded_outcome(
        chunk: TextChunk,
        *,
        category: str,
        code: str,
        message: str,
    ) -> AnnotationChunkOutcome:
        """Represent a rejected model result using the untouched chunk text."""
        return AnnotationChunkOutcome(
            index=chunk.index,
            text=chunk.text,
            issue=ServiceIssue(
                category=category,
                code=code,
                message=message,
                chunk_index=chunk.index,
            ),
        )

    @staticmethod
    async def _emit_progress(
        event_sink: EventSink | None,
        *,
        request_id: str | None,
        current: int,
        total: int,
        stage: str,
        message: str,
        chunk_index: int | None = None,
    ) -> None:
        """Emit completion counts separately from the actual finished chunk."""
        if event_sink is None:
            return
        payload = {
            "current": current,
            "total": total,
            "stage": stage,
            "message": message,
        }
        if chunk_index is not None:
            payload["chunk_index"] = chunk_index
        await emit_backend_event(
            event_sink,
            "annotation.progress",
            request_id=request_id,
            **payload,
        )

    @staticmethod
    async def _emit_degraded(
        event_sink: EventSink | None,
        *,
        request_id: str | None,
        issue: ServiceIssue,
    ) -> None:
        """Expose a classified fallback without turning it into task failure."""
        if event_sink is None:
            return
        await emit_backend_event(
            event_sink,
            "annotation.degraded",
            request_id=request_id,
            chunk_index=issue.chunk_index,
            category=issue.category,
            code=issue.code,
            message=issue.message,
        )

    @staticmethod
    async def _emit_candidate_rejected(
        event_sink: EventSink | None,
        *,
        request_id: str | None,
        issue: ServiceIssue,
    ) -> None:
        """Report one ignored candidate without degrading its whole chunk."""
        if event_sink is None:
            return
        await emit_backend_event(
            event_sink,
            "annotation.candidate_rejected",
            request_id=request_id,
            chunk_index=issue.chunk_index,
            item_index=issue.item_index,
            category=issue.category,
            code=issue.code,
            message=issue.message,
        )

    @staticmethod
    def _retry_event_sink(
        event_sink: EventSink,
        *,
        request_id: str | None,
        chunk_index: int,
    ):
        async def on_retry_wait(message: str) -> None:
            await emit_backend_event(
                event_sink,
                "annotation.model_retry",
                request_id=request_id,
                chunk_index=chunk_index,
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
        event_sink: EventSink | None = None,
        request_id: str | None = None,
        profile_id: str | None = None,
        selection_policy_id: str | None = None,
    ) -> AnnotationResult:
        return await self._get_service(profile_id).annotate_text(
            text,
            mastered_words=mastered_words,
            event_sink=event_sink,
            request_id=request_id,
            profile_id=profile_id,
            selection_policy_id=selection_policy_id,
        )
