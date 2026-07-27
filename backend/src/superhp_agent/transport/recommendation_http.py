"""HTTP adapter for durable book-recommendation conversations.

The router maps public DTOs to the Application Runner and projects stored
Sessions into user-visible messages plus verified catalog cards. It never
exposes internal Tool Calls, Tool Results, prompts, or Provider objects.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from superhp_agent.agents.book_recommendation import RecommendationAgentStateError
from superhp_agent.application import (
    RecommendationAgentRunner,
    RecommendationSessionNotFoundError,
)
from superhp_agent.contracts import (
    RecommendationAgentMessageRole,
    RecommendationAgentSession,
    RecommendationOrigin,
    RecommendationRequest,
)
from superhp_agent.ports import BookDifficultyCatalog
from superhp_agent.schemas import (
    ContinueRecommendationSessionRequest,
    CreateRecommendationSessionRequest,
    RecommendationBookCard,
    RecommendationChatMessage,
    RecommendationSessionResponse,
)


def create_recommendation_router(
    runner: RecommendationAgentRunner,
    catalog: BookDifficultyCatalog,
) -> APIRouter:
    """Create a router bound to explicit Application capabilities."""
    router = APIRouter(
        prefix="/api/recommendations",
        tags=["recommendations"],
    )

    @router.post(
        "/sessions",
        response_model=RecommendationSessionResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_session(
        payload: CreateRecommendationSessionRequest,
    ) -> RecommendationSessionResponse:
        if payload.origin is RecommendationOrigin.DIFFICULTY_ALERT:
            raise HTTPException(
                status_code=400,
                detail=(
                    "difficulty_alert requires a reading handoff and cannot "
                    "be created from the initial recommendation endpoint"
                ),
            )
        request = RecommendationRequest(
            origin=payload.origin,
            preferred_genres=_clean_values(payload.preferred_genres),
            excluded_traits=_clean_values(payload.excluded_traits),
            reading_preference=payload.reading_preference,
            user_notes=payload.user_notes.strip(),
        )
        reply = await runner.start(request)
        return await _public_session(
            reply.session,
            catalog,
            error_code=reply.error_code,
        )

    @router.post(
        "/sessions/{session_id}/messages",
        response_model=RecommendationSessionResponse,
    )
    async def continue_session(
        session_id: str,
        payload: ContinueRecommendationSessionRequest,
    ) -> RecommendationSessionResponse:
        message = payload.message.strip()
        if not message:
            raise HTTPException(status_code=400, detail="message is required")
        try:
            reply = await runner.resume(
                session_id,
                user_message=message,
            )
        except RecommendationSessionNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RecommendationAgentStateError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return await _public_session(
            reply.session,
            catalog,
            error_code=reply.error_code,
        )

    @router.get(
        "/sessions/{session_id}",
        response_model=RecommendationSessionResponse,
    )
    async def get_session(session_id: str) -> RecommendationSessionResponse:
        session = runner.load(session_id)
        if session is None:
            raise HTTPException(
                status_code=404,
                detail=f"recommendation session not found: {session_id}",
            )
        return await _public_session(session, catalog)

    return router


async def _public_session(
    session: RecommendationAgentSession,
    catalog: BookDifficultyCatalog,
    *,
    error_code: str = "",
) -> RecommendationSessionResponse:
    messages = [
        RecommendationChatMessage(
            role=message.role.value,
            content=message.content,
        )
        for message in session.conversation
        if message.role
        in {
            RecommendationAgentMessageRole.USER,
            RecommendationAgentMessageRole.ASSISTANT,
        }
        and message.content.strip()
    ]
    books: list[RecommendationBookCard] = []
    for catalog_id in session.recommended_catalog_ids:
        candidate = await catalog.find_by_id(catalog_id)
        if candidate is None:
            continue
        books.append(
            RecommendationBookCard(
                catalog_id=candidate.catalog_id,
                title_en=candidate.title_en,
                title_zh=candidate.title_zh,
                author=candidate.author,
                entry_kind=candidate.entry_kind,
                lexile_min=candidate.difficulty.minimum_lexile,
                lexile_max=candidate.difficulty.maximum_lexile,
                genres=list(candidate.genres),
            )
        )
    return RecommendationSessionResponse(
        session_id=session.session_id,
        phase=session.phase,
        messages=messages,
        recommended_books=books,
        error_code=error_code or session.error_code,
    )


def _clean_values(values: list[str]) -> tuple[str, ...]:
    """Trim, remove blanks, and preserve the first occurrence order."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        key = normalized.casefold()
        if not normalized or key in seen:
            continue
        seen.add(key)
        cleaned.append(normalized)
    return tuple(cleaned)
