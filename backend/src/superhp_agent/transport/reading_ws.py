"""WebSocket transport for guided reading sessions."""

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
from superhp_agent.schemas import AgentAction
from superhp_agent.storage import AppDB


class ReadingSocketMessage(BaseModel):
    type: str
    request_id: str | None = None
    action: AgentAction | None = None
    current_chapter_id: str | None = None
    current_unit_id: str | None = None


class ReadingSocketSession:
    """Handle one guided-reading WebSocket connection."""

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
        self.current_unit_id: str | None = None

    async def run(self) -> None:
        await self.websocket.accept()
        self._log_event("session_started")
        await self.send_ready()
        await self.send_cards()

        while True:
            raw = await self.websocket.receive_json()
            await self.handle_raw_message(raw)

    async def handle_raw_message(self, raw: dict[str, Any]) -> None:
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
        context = ActionContext(
            corpus=self.corpus,
            emit=self.send_event,
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

        self.current_unit_id = context.current_unit_id
        await self.send_cards(request_id=request_id)

    async def send_ready(self, request_id: str | None = None) -> None:
        await self.send_event(
            "ready",
            request_id=request_id,
            protocol="reading.v1",
        )

    async def send_cards(self, request_id: str | None = None) -> None:
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
        event = {"type": event_type, **payload}
        if request_id is not None:
            event["request_id"] = request_id
        await self.websocket.send_json(event)

    def _log_event(self, event_type: str, **payload: Any) -> None:
        if self.memory_store:
            self.memory_store.log_event(event_type, **payload)