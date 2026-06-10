"""WebSocket transport for guided reading sessions.

The transport understands protocol messages, request ids, and error envelopes.
It does not decide reading flow or perform business side effects directly; those
belong to the router and action dispatcher.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import WebSocket
from pydantic import BaseModel, ValidationError

from superhp_agent.corpus import CorpusError, CorpusStore
from superhp_agent.memory import ReadingMemoryStore
from superhp_agent.runtime.action_dispatcher import (
    ActionContext,
    ActionDispatcher,
    ActionExecutionError,
    AnnotationService,
    MissingActionPayloadError,
    UnsupportedActionError,
)
from superhp_agent.runtime.action_router import ReadingFlowRouter
from superhp_agent.runtime.events import BackendEvent, EventSink
from superhp_agent.schemas import AgentAction
from superhp_agent.storage import AppDB


class ReadingSocketMessage(BaseModel):
    """Validated client message for the reading.v1 protocol."""
    type: str
    request_id: str | None = None
    action: AgentAction | None = None
    current_chapter_id: str | None = None
    current_unit_id: str | None = None


class ReadingSocketEventSink:
    """Forward backend events to one WebSocket client."""

    def __init__(self, websocket: WebSocket):
        self.websocket = websocket

    async def emit_event(self, event: BackendEvent) -> None:
        await self.websocket.send_json(event.as_message())


class ReadingSocketSession:
    """Handle one guided-reading WebSocket connection.

    A session tracks only connection-local state, such as the current unit id.
    Durable progress is written through ReadingMemoryStore by action handlers.
    """

    def __init__(
        self,
        *,
        websocket: WebSocket,
        flow_router: ReadingFlowRouter,
        corpus: CorpusStore,
        memory_store: ReadingMemoryStore | None = None,
        action_dispatcher: ActionDispatcher | None = None,
        annotated_dir: str | Path | None = None,
        annotator_service: AnnotationService | None = None,
        db: AppDB | None = None,
    ):
        self.websocket = websocket
        self.flow_router = flow_router
        self.corpus = corpus
        self.memory_store = memory_store
        self.action_dispatcher = action_dispatcher or ActionDispatcher()
        self.annotated_dir = Path(annotated_dir) if annotated_dir is not None else None
        self.annotator_service = annotator_service
        self.db = db
        self.event_sink: EventSink = ReadingSocketEventSink(websocket)
        self.current_unit_id: str | None = None

    async def run(self) -> None:
        """Accept the socket, send initial cards, then process client messages."""
        await self.websocket.accept()
        self._log_event("session_started")
        await self.send_ready()
        await self.send_cards()

        while True:
            raw = await self.websocket.receive_json()
            await self.handle_raw_message(raw)

    async def handle_raw_message(self, raw: dict[str, Any]) -> None:
        """Validate and route one raw JSON message from the frontend."""
        try:
            message = ReadingSocketMessage.model_validate(raw)
        except ValidationError as exc:
            await self.send_error(
                code="invalid_message",
                message="消息格式不正确。",
                detail=exc.errors(),
            )
            return

        if message.type == "hello":
            if message.current_unit_id or message.current_chapter_id:
                self.current_unit_id = message.current_unit_id or message.current_chapter_id
            self._log_event("session_hello", current_unit_id=self.current_unit_id)
            await self.send_ready(request_id=message.request_id)
            await self.send_cards(request_id=message.request_id)
            return

        if message.type == "ping":
            await self.send_event("pong", request_id=message.request_id)
            return

        if message.type == "action":
            if message.action is None:
                await self.send_error(
                    code="missing_action",
                    message="action 消息缺少 action 内容。",
                    request_id=message.request_id,
                )
                return
            await self.handle_action(message.action, request_id=message.request_id)
            return

        await self.send_error(
            code="unknown_message_type",
            message=f"未知消息类型：{message.type}",
            request_id=message.request_id,
        )

    async def handle_action(
        self,
        action: AgentAction,
        *,
        request_id: str | None = None,
    ) -> None:
        # ActionContext is the explicit capability bundle for handlers. This is
        # the boundary that keeps transport concerns out of business logic.
        context = ActionContext(
            corpus=self.corpus,
            event_sink=self.event_sink,
            memory_store=self.memory_store,
            annotated_dir=self.annotated_dir,
            annotator_service=self.annotator_service,
            db=self.db,
            current_unit_id=self.current_unit_id,
        )
        try:
            await self.action_dispatcher.dispatch(action, context, request_id=request_id)
        except MissingActionPayloadError as exc:
            await self.send_error(
                code=f"missing_{exc.field_name}",
                message=f"该 action 缺少 {exc.field_name}。",
                request_id=request_id,
            )
            return
        except ActionExecutionError as exc:
            await self.send_error(
                code=exc.code,
                message=exc.message,
                request_id=request_id,
            )
            return
        except CorpusError as exc:
            await self.send_error(
                code="unit_not_found",
                message=str(exc),
                request_id=request_id,
            )
            return
        except UnsupportedActionError as exc:
            await self.send_error(
                code="unsupported_action",
                message=f"暂不支持该 action：{exc.action_id}",
                request_id=request_id,
            )
            return
        except Exception as exc:
            self._log_event("internal_error", error=str(exc), request_id=request_id)
            await self.send_error(
                code="internal_error",
                message="后端执行 action 时发生未知错误。",
                request_id=request_id,
            )
            return

        self.current_unit_id = context.current_unit_id
        await self.send_cards(request_id=request_id)

    async def send_ready(self, request_id: str | None = None) -> None:
        await self.send_event(
            "ready",
            request_id=request_id,
            protocol="reading.v1",
        )

    async def send_cards(self, request_id: str | None = None) -> None:
        """Ask the deterministic router for fresh choices and push them down."""
        cards = self.flow_router.inspect(current_unit_id=self.current_unit_id)
        self._log_event("cards_shown", current_unit_id=self.current_unit_id, card_ids=[card.id for card in cards])
        await self.send_event(
            "cards.updated",
            request_id=request_id,
            current_chapter_id=self.current_unit_id,
            current_unit_id=self.current_unit_id,
            cards=[card.model_dump() for card in cards],
        )

    async def send_error(
        self,
        *,
        code: str,
        message: str,
        request_id: str | None = None,
        detail: Any | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "code": code,
            "message": message,
        }
        if detail is not None:
            payload["detail"] = detail
        self._log_event("error", code=code, request_id=request_id)
        await self.send_event("error", request_id=request_id, error=payload)

    async def send_event(
        self,
        event_type: str,
        *,
        request_id: str | None = None,
        **payload: Any,
    ) -> None:
        await self.event_sink.emit_event(BackendEvent(type=event_type, request_id=request_id, payload=payload))

    def _log_event(self, event_type: str, **payload: Any) -> None:
        if self.memory_store:
            self.memory_store.log_event(event_type, **payload)