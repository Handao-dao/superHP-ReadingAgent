"""Action execution layer for guided reading flows."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from superhp_agent.corpus import CorpusStore, ReadingUnitDocument
from superhp_agent.memory import ReadingMemoryStore
from superhp_agent.runtime.actions import (
    GENERATE_ANNOTATION,
    MARK_CHAPTER_READ,
    OPEN_ANNOTATED_COPY,
    OPEN_CHAPTER,
    READ_ORIGINAL,
    START_NEXT_CHAPTER,
)
from superhp_agent.schemas import AgentAction, ReadingUnitDetail, ReadingUnitMeta
from superhp_agent.services.annotator import AnnotationResult
from superhp_agent.storage import AppDB

EventEmitter = Callable[..., Awaitable[None]]


class AnnotationService(Protocol):
    async def annotate_text(
        self,
        text: str,
        *,
        mastered_words: list[str] | None = None,
        level: str = "intermediate",
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
    corpus: CorpusStore
    emit: EventEmitter
    memory_store: ReadingMemoryStore | None = None
    annotated_dir: Path | None = None
    annotator_service: AnnotationService | None = None
    db: AppDB | None = None
    current_unit_id: str | None = None

    def log_event(self, event_type: str, **payload: Any) -> None:
        if self.memory_store:
            self.memory_store.log_event(event_type, **payload)


class ActionHandler(Protocol):
    async def handle(
        self,
        action: AgentAction,
        context: ActionContext,
        *,
        request_id: str | None = None,
    ) -> None: ...


class ActionDispatcher:
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
    async def handle(
        self,
        action: AgentAction,
        context: ActionContext,
        *,
        request_id: str | None = None,
    ) -> None:
        unit_id = _require_unit_id(action.payload)
        await context.emit(
            "chapter.loading",
            request_id=request_id,
            chapter_id=unit_id,
            unit_id=unit_id,
            body_kind="source",
        )
        doc = context.corpus.get_unit(unit_id)
        context.current_unit_id = doc.meta.id
        if context.memory_store:
            context.memory_store.mark_opened(doc.meta.id)
        await _emit_opened_unit(
            context,
            doc,
            body=doc.body,
            body_kind="source",
            request_id=request_id,
            action_id=action.id,
        )


class OpenAnnotatedUnitHandler:
    async def handle(
        self,
        action: AgentAction,
        context: ActionContext,
        *,
        request_id: str | None = None,
    ) -> None:
        unit_id = _require_unit_id(action.payload)
        annotated_path = _annotated_path(context, unit_id)
        if not annotated_path.exists():
            raise ActionExecutionError("annotated_copy_not_found", "还没有生成这一节的译注副本。")

        await context.emit(
            "chapter.loading",
            request_id=request_id,
            chapter_id=unit_id,
            unit_id=unit_id,
            body_kind="annotated",
        )
        doc = context.corpus.get_unit(unit_id)
        context.current_unit_id = doc.meta.id
        if context.memory_store:
            context.memory_store.mark_opened(doc.meta.id)
        _, body = _split_annotated_file(annotated_path.read_text(encoding="utf-8"))
        await _emit_opened_unit(
            context,
            doc,
            body=body.strip(),
            body_kind="annotated",
            request_id=request_id,
            action_id=action.id,
        )


class MarkReadHandler:
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
        if context.memory_store:
            context.memory_store.mark_read(unit_id)
        await context.emit(
            "unit.marked_read",
            request_id=request_id,
            chapter_id=unit_id,
            unit_id=unit_id,
        )


class GenerateAnnotationHandler:
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
        if context.annotator_service is None:
            raise ActionExecutionError("annotator_not_configured", "译注服务尚未配置模型 provider。")

        context.log_event("annotation_requested", unit_id=unit_id)
        await context.emit("annotation.started", request_id=request_id, unit_id=unit_id, chapter_id=unit_id)
        doc = context.corpus.get_unit(unit_id)
        context.current_unit_id = doc.meta.id

        await context.emit(
            "annotation.progress",
            request_id=request_id,
            unit_id=unit_id,
            chapter_id=unit_id,
            stage="llm",
            message="正在生成译注...",
        )
        try:
            result = await context.annotator_service.annotate_text(doc.body)
        except Exception as exc:
            context.log_event("annotation_failed", unit_id=unit_id, error=str(exc))
            await context.emit(
                "annotation.failed",
                request_id=request_id,
                unit_id=unit_id,
                chapter_id=unit_id,
                message=str(exc),
            )
            return

        annotated_path = _annotated_path(context, unit_id)
        annotated_path.parent.mkdir(parents=True, exist_ok=True)
        annotated_path.write_text(_render_annotated_markdown(doc, result), encoding="utf-8")
        stored_vocabulary_count = 0
        if context.db:
            stored_vocabulary_count = context.db.add_vocabulary_items(doc.meta, result.vocabulary)
        if context.memory_store:
            context.memory_store.mark_annotated(unit_id)
        context.log_event(
            "annotation_completed",
            unit_id=unit_id,
            vocabulary_count=len(result.vocabulary),
            stored_vocabulary_count=stored_vocabulary_count,
        )

        await context.emit(
            "annotation.completed",
            request_id=request_id,
            unit_id=unit_id,
            chapter_id=unit_id,
            vocabulary_count=len(result.vocabulary),
            stored_vocabulary_count=stored_vocabulary_count,
        )
        await _emit_opened_unit(
            context,
            doc,
            body=result.annotated_text,
            body_kind="annotated",
            request_id=request_id,
            action_id=action.id,
        )


def default_action_handlers() -> dict[str, ActionHandler]:
    open_handler = OpenUnitHandler()
    return {
        OPEN_CHAPTER: open_handler,
        READ_ORIGINAL: open_handler,
        START_NEXT_CHAPTER: open_handler,
        OPEN_ANNOTATED_COPY: OpenAnnotatedUnitHandler(),
        MARK_CHAPTER_READ: MarkReadHandler(),
        GENERATE_ANNOTATION: GenerateAnnotationHandler(),
    }


def _payload_unit_id(payload: dict[str, Any]) -> str:
    value = payload.get("unit_id") or payload.get("chapter_id")
    return str(value) if value else ""


def _require_unit_id(payload: dict[str, Any]) -> str:
    unit_id = _payload_unit_id(payload)
    if not unit_id:
        raise MissingActionPayloadError("unit_id")
    return unit_id


def _annotated_path(context: ActionContext, unit_id: str) -> Path:
    if context.annotated_dir is None:
        raise ActionExecutionError("annotated_dir_not_configured", "译注副本目录尚未配置。")
    return context.annotated_dir / f"{unit_id}.annotated.md"


async def _emit_opened_unit(
    context: ActionContext,
    doc: ReadingUnitDocument,
    *,
    body: str,
    body_kind: str,
    request_id: str | None,
    action_id: str,
) -> None:
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
        ),
        body=body,
        body_kind=body_kind,
    )
    await context.emit(
        "chapter.opened",
        request_id=request_id,
        action_id=action_id,
        chapter=detail.model_dump(),
        unit=detail.model_dump(),
    )


def _render_annotated_markdown(doc: ReadingUnitDocument, result: AnnotationResult) -> str:
    vocab_lines = "\n".join(
        f"# - {item.word}: {item.translation}"
        for item in result.vocabulary
        if item.word or item.translation
    )
    annotated_at = datetime.now(UTC).isoformat()
    return (
        "---\n"
        f"source_unit_id: {doc.meta.id}\n"
        f"chapter_id: {doc.meta.chapter_id}\n"
        f"book_id: {doc.meta.book_id}\n"
        f"chapter_no: {doc.meta.chapter_no}\n"
        f"section_no: {doc.meta.section_no}\n"
        f"section_count: {doc.meta.section_count}\n"
        "body_kind: annotated\n"
        f"annotated_at: {annotated_at}\n"
        "---\n\n"
        f"<!-- extracted_vocabulary\n{vocab_lines}\n-->\n\n"
        f"{result.annotated_text.strip()}\n"
    )


def _split_annotated_file(raw: str) -> tuple[str, str]:
    if not raw.startswith("---"):
        return "", raw
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return "", raw
    return parts[1], parts[2]