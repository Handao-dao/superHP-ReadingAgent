"""Action execution layer for guided reading flows.

The router decides which choices to display; this module decides what happens
after the user chooses one. Keeping those layers separate makes side effects
like memory writes, annotation generation, and file creation easy to audit.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from superhp_agent.artifacts import AnnotatedCopyStore
from superhp_agent.contracts import AgentAction, ReadingUnitDetail, ReadingUnitMeta
from superhp_agent.contracts.annotation import AnnotationResult
from superhp_agent.corpus import CorpusStore, ReadingUnitDocument
from superhp_agent.memory import ReadingMemoryStore
from superhp_agent.ports.events import EventEmitter, EventSink, emit_backend_event
from superhp_agent.ports.repositories import (
    ReadingProgressRepository,
    VocabularyRepository,
)
from superhp_agent.prompts import normalize_level
from superhp_agent.runtime.actions import (
    GENERATE_ANNOTATION,
    MARK_CHAPTER_READ,
    OPEN_ANNOTATED_COPY,
    OPEN_CHAPTER,
    READ_ORIGINAL,
    START_NEXT_CHAPTER,
)
from superhp_agent.runtime.events import (
    CallableEventSink,
)


class AnnotationService(Protocol):
    """Minimal annotator capability required by the generate action."""
    async def annotate_text(
        self,
        text: str,
        *,
        mastered_words: list[str] | None = None,
        level: str = "intermediate",
        event_sink: EventSink | None = None,
        request_id: str | None = None,
        profile_id: str | None = None,
    ) -> AnnotationResult: ...


class UnsupportedActionError(ValueError):
    def __init__(self, action_id: str):
        super().__init__(f"Unsupported action: {action_id}")
        self.action_id = action_id


class MissingActionPayloadError(ValueError):
    def __init__(self, field_name: str):
        super().__init__(f"Missing action payload: {field_name}")
        self.field_name = field_name


class ActionExecutionError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ActionContext:
    """Explicit capability bundle passed from transport to action handlers.

    Handlers only receive what they need: corpus reads, event emission, optional
    memory/storage services, and the connection's current unit id.
    """
    corpus: CorpusStore
    emit: EventEmitter | None = None
    event_sink: EventSink | None = None
    memory_store: ReadingMemoryStore | None = None
    progress_repository: ReadingProgressRepository | None = None
    annotated_dir: Path | None = None
    annotated_copies: AnnotatedCopyStore | None = None
    annotator_service: AnnotationService | None = None
    db: VocabularyRepository | None = None
    current_unit_id: str | None = None

    def __post_init__(self) -> None:
        if self.event_sink is None and self.emit is not None:
            self.event_sink = CallableEventSink(self.emit)
        if self.annotated_copies is None and self.annotated_dir is not None:
            self.annotated_copies = AnnotatedCopyStore(self.annotated_dir)
        # Compatibility for tests and older composition code during the JSON
        # to SQLite transition. Production injects the new repository.
        if self.progress_repository is None and self.memory_store is not None:
            self.progress_repository = self.memory_store

    async def emit_event(
        self,
        event_type: str,
        *,
        request_id: str | None = None,
        **payload: Any,
    ) -> None:
        if self.event_sink is not None:
            await emit_backend_event(self.event_sink, event_type, request_id=request_id, **payload)

    def log_event(self, event_type: str, **payload: Any) -> None:
        if self.memory_store:
            self.memory_store.log_event(event_type, **payload)

    def require_annotated_copies(self) -> AnnotatedCopyStore:
        """Return the artifact capability or raise the existing action error."""
        if self.annotated_copies is None:
            raise ActionExecutionError("annotated_dir_not_configured", "译注副本目录尚未配置。")
        return self.annotated_copies


class ActionHandler(Protocol):
    """Common interface for one user-selectable action."""
    async def handle(
        self,
        action: AgentAction,
        context: ActionContext,
        *,
        request_id: str | None = None,
    ) -> None: ...


class ActionDispatcher:
    """Map action ids to handler objects and run the selected action."""
    def __init__(self, handlers: dict[str, ActionHandler] | None = None):
        self.handlers = handlers or default_action_handlers()

    async def dispatch(
        self,
        action: AgentAction,
        context: ActionContext,
        *,
        request_id: str | None = None,
    ) -> None:
        handler = self.handlers.get(action.id)
        if handler is None:
            raise UnsupportedActionError(action.id)
        await handler.handle(action, context, request_id=request_id)


class OpenUnitHandler:
    """Open source Markdown and mark it as the active unit."""
    async def handle(
        self,
        action: AgentAction,
        context: ActionContext,
        *,
        request_id: str | None = None,
    ) -> None:
        unit_id = _require_unit_id(action.payload)
        await context.emit_event(
            "chapter.loading",
            request_id=request_id,
            chapter_id=unit_id,
            unit_id=unit_id,
            body_kind="source",
        )
        doc = context.corpus.get_unit(unit_id)
        context.current_unit_id = doc.meta.id
        if context.progress_repository:
            context.progress_repository.mark_opened(doc.meta.id)
        await _emit_opened_unit(
            context,
            doc,
            body=doc.body,
            body_kind="source",
            request_id=request_id,
            action_id=action.id,
        )


class OpenAnnotatedUnitHandler:
    """Open a generated annotated copy, creating the selected density if needed."""

    def __init__(self, generator: GenerateAnnotationHandler | None = None):
        self.generator = generator or GenerateAnnotationHandler()

    async def handle(
        self,
        action: AgentAction,
        context: ActionContext,
        *,
        request_id: str | None = None,
    ) -> None:
        unit_id = _require_unit_id(action.payload)
        level = _payload_level(action.payload)
        # The annotated copy is the user's durable reading artifact; DB writes
        # are secondary indexes for vocabulary review.
        annotated_copy = context.require_annotated_copies().read(unit_id, level)
        if annotated_copy is None:
            await self.generator.handle(action, context, request_id=request_id)
            return

        await context.emit_event(
            "chapter.loading",
            request_id=request_id,
            chapter_id=unit_id,
            unit_id=unit_id,
            body_kind="annotated",
        )
        doc = context.corpus.get_unit(unit_id)
        context.current_unit_id = doc.meta.id
        if context.progress_repository:
            context.progress_repository.mark_opened(doc.meta.id)
        await _emit_opened_unit(
            context,
            doc,
            body=annotated_copy.body,
            body_kind="annotated",
            request_id=request_id,
            action_id=action.id,
        )


class MarkReadHandler:
    """Mark the current or provided unit as completed."""
    async def handle(
        self,
        action: AgentAction,
        context: ActionContext,
        *,
        request_id: str | None = None,
    ) -> None:
        unit_id = _payload_unit_id(action.payload) or context.current_unit_id
        if not unit_id:
            raise MissingActionPayloadError("unit_id")

        context.current_unit_id = unit_id
        if context.progress_repository:
            context.progress_repository.mark_read(unit_id)
        await context.emit_event(
            "unit.marked_read",
            request_id=request_id,
            chapter_id=unit_id,
            unit_id=unit_id,
        )


class StartNextUnitHandler:
    """Complete the current unit and move the session pointer to the next unit."""
    async def handle(
        self,
        action: AgentAction,
        context: ActionContext,
        *,
        request_id: str | None = None,
    ) -> None:
        next_unit_id = _require_unit_id(action.payload)
        completed_unit_id = str(action.payload.get("completed_unit_id") or context.current_unit_id or "")
        if completed_unit_id and context.progress_repository:
            context.progress_repository.mark_read(completed_unit_id)
            await context.emit_event(
                "unit.marked_read",
                request_id=request_id,
                chapter_id=completed_unit_id,
                unit_id=completed_unit_id,
            )

        context.corpus.get_unit(next_unit_id)
        context.current_unit_id = next_unit_id
        if context.progress_repository:
            context.progress_repository.mark_opened(next_unit_id)


class GenerateAnnotationHandler:
    """Generate, persist, and return an annotated copy for one unit."""
    async def handle(
        self,
        action: AgentAction,
        context: ActionContext,
        *,
        request_id: str | None = None,
    ) -> None:
        unit_id = _payload_unit_id(action.payload) or context.current_unit_id
        level = _payload_level(action.payload)
        if not unit_id:
            raise MissingActionPayloadError("unit_id")
        if context.annotator_service is None:
            raise ActionExecutionError("annotator_not_configured", "译注服务尚未配置模型 provider。")

        context.log_event("annotation_requested", unit_id=unit_id)
        await context.emit_event("annotation.started", request_id=request_id, unit_id=unit_id, chapter_id=unit_id)
        doc = context.corpus.get_unit(unit_id)
        context.current_unit_id = doc.meta.id

        # Emit progress before the model call so the frontend can show useful
        # feedback during longer annotation runs.
        await context.emit_event(
            "annotation.progress",
            request_id=request_id,
            unit_id=unit_id,
            chapter_id=unit_id,
            stage="llm",
            message="正在生成译注...",
        )
        try:
            mastered_words = context.db.list_mastered_words() if context.db else []
            result = await context.annotator_service.annotate_text(
                doc.body,
                mastered_words=mastered_words,
                level=level,
                event_sink=context.event_sink,
                request_id=request_id,
                profile_id=doc.meta.profile_id,
            )
        except Exception as exc:
            context.log_event("annotation_failed", unit_id=unit_id, error=str(exc))
            await context.emit_event(
                "annotation.failed",
                request_id=request_id,
                unit_id=unit_id,
                chapter_id=unit_id,
                message=str(exc),
            )
            return

        # A mixed result remains useful and can be saved. If every chunk fell
        # back, return the readable source text without recording a fake
        # annotated copy, so the user can retry later.
        persisted = not result.fully_degraded
        status = "degraded" if result.issues else "completed"
        stored_vocabulary_count = 0
        if persisted:
            context.require_annotated_copies().write(
                doc,
                annotated_text=result.annotated_text,
                vocabulary=result.vocabulary,
                level=level,
                status=status,
                validated_chunk_count=result.validated_chunk_count,
                total_chunk_count=result.total_chunk_count,
            )
            if context.db:
                stored_vocabulary_count = context.db.add_vocabulary_items(
                    doc.meta,
                    result.vocabulary,
                )
        provider_error_count = sum(
            issue.category == "provider" for issue in result.issues
        )
        validation_error_count = sum(
            issue.category == "validation" for issue in result.issues
        )
        context.log_event(
            "annotation_completed",
            unit_id=unit_id,
            status=status,
            persisted=persisted,
            vocabulary_count=len(result.vocabulary),
            stored_vocabulary_count=stored_vocabulary_count,
            degraded_chunk_count=len(result.issues),
        )

        await context.emit_event(
            "annotation.completed",
            request_id=request_id,
            unit_id=unit_id,
            chapter_id=unit_id,
            status=status,
            persisted=persisted,
            vocabulary_count=len(result.vocabulary),
            stored_vocabulary_count=stored_vocabulary_count,
            validated_chunk_count=result.validated_chunk_count,
            total_chunk_count=result.total_chunk_count,
            degraded_chunk_count=len(result.issues),
            provider_error_count=provider_error_count,
            validation_error_count=validation_error_count,
        )
        await _emit_opened_unit(
            context,
            doc,
            body=result.annotated_text,
            body_kind="annotated" if persisted else "original",
            request_id=request_id,
            action_id=action.id,
        )


def default_action_handlers() -> dict[str, ActionHandler]:
    """Register v1 action ids with their deterministic handlers."""
    open_handler = OpenUnitHandler()
    generate_handler = GenerateAnnotationHandler()
    return {
        OPEN_CHAPTER: open_handler,
        READ_ORIGINAL: open_handler,
        START_NEXT_CHAPTER: StartNextUnitHandler(),
        OPEN_ANNOTATED_COPY: OpenAnnotatedUnitHandler(generate_handler),
        MARK_CHAPTER_READ: MarkReadHandler(),
        GENERATE_ANNOTATION: generate_handler,
    }


def _payload_unit_id(payload: dict[str, Any]) -> str:
    """Accept both new unit_id and legacy chapter_id payload names."""
    value = payload.get("unit_id") or payload.get("chapter_id")
    return str(value) if value else ""


def _require_unit_id(payload: dict[str, Any]) -> str:
    unit_id = _payload_unit_id(payload)
    if not unit_id:
        raise MissingActionPayloadError("unit_id")
    return unit_id


def _payload_level(payload: dict[str, Any]) -> str:
    return normalize_level(str(payload.get("level") or "intermediate"))


async def _emit_opened_unit(
    context: ActionContext,
    doc: ReadingUnitDocument,
    *,
    body: str,
    body_kind: str,
    request_id: str | None,
    action_id: str,
) -> None:
    # Keep legacy chapter fields in the payload while the frontend migrates to
    # reading-unit terminology.
    detail = ReadingUnitDetail(
        meta=ReadingUnitMeta(
            id=doc.meta.id,
            chapter_id=doc.meta.chapter_id,
            book_id=doc.meta.book_id,
            book_title=doc.meta.book_title,
            chapter_no=doc.meta.chapter_no,
            chapter_title=doc.meta.chapter_title,
            section_no=doc.meta.section_no,
            section_count=doc.meta.section_count,
            summary=doc.meta.summary,
            has_annotated_copy=body_kind == "annotated",
            profile_id=doc.meta.profile_id,
        ),
        body=body,
        body_kind=body_kind,
    )
    await context.emit_event(
        "chapter.opened",
        request_id=request_id,
        action_id=action_id,
        chapter=detail.model_dump(),
        unit=detail.model_dump(),
    )
