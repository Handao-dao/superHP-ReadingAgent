"""WebSocket transport for guided reading sessions.

The transport understands protocol messages, request ids, and error envelopes.
It does not decide reading flow or perform business side effects directly; those
belong to the router and action dispatcher.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import WebSocket
from pydantic import BaseModel, ConfigDict, ValidationError

from superhp_agent.artifacts import AnnotatedCopyStore
from superhp_agent.contracts import AgentAction, BackendEvent
from superhp_agent.corpus import CorpusError, CorpusStore
from superhp_agent.ports.events import EventLogger, EventSink
from superhp_agent.ports.repositories import (
    ReadingDifficultyPromptRepository,
    ReadingProgressRepository,
    ReadingSupportRepository,
    VocabularyRepository,
)
from superhp_agent.profiles import ProfileRegistry, UnknownProfileError
from superhp_agent.runtime.action_dispatcher import (
    ActionContext,
    ActionDispatcher,
    ActionExecutionError,
    AnnotationService,
    ChapterCheckpointCapability,
    MissingActionPayloadError,
    ReadingAdaptationEvaluationCapability,
    SelectionPolicyResolver,
    UnsupportedActionError,
)
from superhp_agent.runtime.action_router import ReadingFlowRouter
from superhp_agent.transport.event_mapper import event_to_websocket_message


class ReadingSocketMessage(BaseModel):
    """Validated client message for the reading.v1 protocol."""
    model_config = ConfigDict(extra="forbid")

    type: str
    request_id: str | None = None
    action: AgentAction | None = None
    current_unit_id: str | None = None
    profile_id: str | None = None
    phase: str | None = None


class ReadingSocketEventSink:
    """Forward backend events to one WebSocket client."""

    def __init__(self, websocket: WebSocket):
        self.websocket = websocket

    async def emit_event(self, event: BackendEvent) -> None:
        await self.websocket.send_json(event_to_websocket_message(event))


class ReadingSocketSession:
    """Handle one guided-reading WebSocket connection.

    A session tracks only connection-local state, such as the current unit id.
    Durable progress is written through ReadingProgressRepository by action handlers.
    """

    def __init__(
        self,
        *,
        websocket: WebSocket,
        flow_router: ReadingFlowRouter,
        corpus: CorpusStore,
        event_log_store: EventLogger | None = None,
        progress_repository: ReadingProgressRepository | None = None,
        action_dispatcher: ActionDispatcher | None = None,
        annotated_dir: str | Path | None = None,
        annotated_copies: AnnotatedCopyStore | None = None,
        annotator_service: AnnotationService | None = None,
        db: VocabularyRepository | None = None,
        reading_support_repository: ReadingSupportRepository | None = None,
        reading_difficulty_prompt_repository: (
            ReadingDifficultyPromptRepository | None
        ) = None,
        chapter_checkpoint_recorder: ChapterCheckpointCapability | None = None,
        reading_adaptation_evaluator: (
            ReadingAdaptationEvaluationCapability | None
        ) = None,
        selection_policy_resolver: SelectionPolicyResolver | None = None,
        profile_registry: ProfileRegistry | None = None,
    ):
        self.websocket = websocket
        self.flow_router = flow_router
        self.corpus = corpus
        self.event_log_store = event_log_store
        self.progress_repository = progress_repository
        self.action_dispatcher = action_dispatcher or ActionDispatcher()
        self.annotated_dir = Path(annotated_dir) if annotated_dir is not None else None
        self.annotated_copies = annotated_copies or (
            AnnotatedCopyStore(self.annotated_dir) if self.annotated_dir is not None else None
        )
        self.annotator_service = annotator_service
        self.db = db
        self.reading_support_repository = reading_support_repository
        self.reading_difficulty_prompt_repository = (
            reading_difficulty_prompt_repository
        )
        self.chapter_checkpoint_recorder = chapter_checkpoint_recorder
        self.reading_adaptation_evaluator = reading_adaptation_evaluator
        self.selection_policy_resolver = selection_policy_resolver
        self.profile_registry = profile_registry
        self.event_sink: EventSink = ReadingSocketEventSink(websocket)
        self.current_unit_id: str | None = None
        self.current_profile_id: str | None = None

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
            if message.profile_id:
                if not await self.select_profile(
                    message.profile_id,
                    request_id=message.request_id,
                ):
                    return
                self.current_profile_id = message.profile_id
            if message.current_unit_id:
                self.current_unit_id = message.current_unit_id
            self._log_event(
                "session_hello",
                current_unit_id=self.current_unit_id,
                profile_id=self.current_profile_id,
            )
            await self.send_ready(request_id=message.request_id)
            await self.send_cards(request_id=message.request_id)
            return

        if message.type == "ping":
            await self.send_event("pong", request_id=message.request_id)
            return

        if message.type == "cards":
            if message.profile_id:
                if not await self.select_profile(
                    message.profile_id,
                    request_id=message.request_id,
                ):
                    return
                self.current_profile_id = message.profile_id
            if message.current_unit_id:
                self.current_unit_id = message.current_unit_id
            await self.send_cards(request_id=message.request_id, phase=message.phase or "start")
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

    async def select_profile(
        self,
        profile_id: str,
        *,
        request_id: str | None = None,
    ) -> bool:
        """Validate a transport Profile id before changing session state."""
        if self.profile_registry is None:
            return True
        try:
            self.profile_registry.get(profile_id)
        except UnknownProfileError as exc:
            await self.send_error(
                code="unknown_profile",
                message=str(exc),
                request_id=request_id,
            )
            return False
        return True

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
            event_log_store=self.event_log_store,
            progress_repository=self.progress_repository,
            annotated_dir=self.annotated_dir,
            annotated_copies=self.annotated_copies,
            annotator_service=self.annotator_service,
            db=self.db,
            reading_support_repository=self.reading_support_repository,
            reading_difficulty_prompt_repository=(
                self.reading_difficulty_prompt_repository
            ),
            chapter_checkpoint_recorder=self.chapter_checkpoint_recorder,
            reading_adaptation_evaluator=self.reading_adaptation_evaluator,
            selection_policy_resolver=self.selection_policy_resolver,
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

    async def send_cards(self, request_id: str | None = None, *, phase: str = "start") -> None:
        """Ask the deterministic router for fresh choices and push them down."""
        resolved_unit_id = self.flow_router.resolve_unit_id(
            current_unit_id=self.current_unit_id,
            profile_id=self.current_profile_id,
        )
        cards = self.flow_router.inspect(
            current_unit_id=resolved_unit_id,
            phase=phase,
            profile_id=self.current_profile_id,
        )
        self.current_unit_id = resolved_unit_id
        self._log_event(
            "cards_shown",
            current_unit_id=resolved_unit_id,
            profile_id=self.current_profile_id,
            phase=phase,
            card_ids=[card.id for card in cards],
        )
        await self.send_event(
            "cards.updated",
            request_id=request_id,
            current_unit_id=resolved_unit_id,
            profile_id=self.current_profile_id,
            phase=phase,
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
        if self.event_log_store:
            self.event_log_store.log_event(event_type, **payload)
