"""HTTP adapter for durable manual reading-companion conversations.

Only public user/assistant messages cross this boundary. Prompts, trusted
scope, Tool Calls, and Tool Results remain internal to the Agent runtime.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from superhp_agent.agents import ReadingCompanionStateError
from superhp_agent.application import (
    ManualReadingCompanionError,
    ReadingCompanionSessionConflictError,
    ReadingCompanionSessionCoordinator,
    ReadingCompanionSessionNotFoundError,
)
from superhp_agent.contracts import (
    ReadingCompanionMessageRole,
    ReadingCompanionRunState,
)
from superhp_agent.schemas import (
    ContinueReadingCompanionSessionRequest,
    CreateReadingCompanionSessionRequest,
    EndReadingCompanionEpisodeRequest,
    ReadingCompanionChatMessage,
    ReadingCompanionMemoryResponse,
    ReadingCompanionSessionEnvelope,
    ReadingCompanionSessionResponse,
)


def create_reading_companion_router(
    coordinator: ReadingCompanionSessionCoordinator,
) -> APIRouter:
    """Create a router bound to the durable companion coordinator."""
    router = APIRouter(
        prefix="/api/reading-companion",
        tags=["reading-companion"],
    )

    @router.post(
        "/sessions",
        response_model=ReadingCompanionSessionResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_session(
        payload: CreateReadingCompanionSessionRequest,
    ) -> ReadingCompanionSessionResponse:
        current_unit_id = payload.current_unit_id.strip()
        message = payload.message.strip()
        if not current_unit_id:
            raise HTTPException(
                status_code=400,
                detail="current_unit_id is required",
            )
        if not message:
            raise HTTPException(status_code=400, detail="message is required")
        try:
            reply = await coordinator.start(
                session_id=payload.session_id.strip() or None,
                current_unit_id=current_unit_id,
                user_message=message,
                selected_text=payload.selected_text.strip(),
            )
        except ReadingCompanionSessionConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ManualReadingCompanionError as exc:
            raise _manual_error(exc) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _public_session(reply.state, error_code=reply.error_code)

    @router.post(
        "/sessions/{session_id}/messages",
        response_model=ReadingCompanionSessionResponse,
    )
    async def continue_session(
        session_id: str,
        payload: ContinueReadingCompanionSessionRequest,
    ) -> ReadingCompanionSessionResponse:
        message = payload.message.strip()
        if not message:
            raise HTTPException(status_code=400, detail="message is required")
        try:
            reply = await coordinator.resume(
                session_id,
                user_message=message,
            )
        except ReadingCompanionSessionNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ManualReadingCompanionError as exc:
            raise _manual_error(exc) from exc
        except ReadingCompanionStateError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _public_session(reply.state, error_code=reply.error_code)

    @router.post(
        "/sessions/{session_id}/retry",
        response_model=ReadingCompanionSessionResponse,
    )
    async def retry_session(
        session_id: str,
    ) -> ReadingCompanionSessionResponse:
        """Retry one recoverable turn without duplicating user content."""
        try:
            reply = await coordinator.retry(session_id)
        except ReadingCompanionSessionNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ManualReadingCompanionError as exc:
            raise _manual_error(exc) from exc
        except ReadingCompanionStateError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _public_session(reply.state, error_code=reply.error_code)

    @router.post(
        "/sessions/{session_id}/end",
        response_model=ReadingCompanionMemoryResponse,
    )
    async def end_episode(
        session_id: str,
        payload: EndReadingCompanionEpisodeRequest,
    ) -> ReadingCompanionMemoryResponse:
        """Close the active Episode before generating its passive summary."""
        try:
            memory = await coordinator.end(
                session_id,
                reason=payload.reason,
            )
        except ReadingCompanionSessionNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return ReadingCompanionMemoryResponse(
            session_id=memory.session_id,
            episode_id=memory.episode_id,
            kind=memory.kind,
            revision=memory.revision,
            status=memory.status,
            summary=memory.summary,
            error_code=memory.error_code,
        )

    @router.get(
        "/sessions/{session_id}",
        response_model=ReadingCompanionSessionEnvelope,
    )
    async def get_session(
        session_id: str,
    ) -> ReadingCompanionSessionEnvelope:
        session = coordinator.load_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=404,
                detail=f"reading companion session not found: {session_id}",
            )
        state = coordinator.load(session.session_id)
        return ReadingCompanionSessionEnvelope(
            session_id=session.session_id,
            status=session.status,
            active_episode=(
                _public_session(state) if state is not None else None
            ),
        )

    return router


def _public_session(
    state: ReadingCompanionRunState,
    *,
    error_code: str = "",
) -> ReadingCompanionSessionResponse:
    episode = state.episode
    return ReadingCompanionSessionResponse(
        session_id=episode.session_id,
        episode_id=episode.episode_id,
        trigger=episode.trigger,
        book_id=episode.book_id,
        chapter_id=episode.chapter_id,
        unit_id=episode.unit_id,
        selected_text=episode.selected_text,
        messages=[
            ReadingCompanionChatMessage(
                role=message.role.value,
                content=message.content,
            )
            for message in state.conversation
            if message.role
            in {
                ReadingCompanionMessageRole.USER,
                ReadingCompanionMessageRole.ASSISTANT,
            }
            and message.content.strip()
        ],
        error_code=error_code or state.error_code,
    )


def _manual_error(exc: ManualReadingCompanionError) -> HTTPException:
    status_code = 404 if exc.code == "no_active_reading" else 409
    return HTTPException(status_code=status_code, detail=str(exc))
