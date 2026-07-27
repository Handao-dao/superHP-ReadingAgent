"""Application boundary for durable recommendation Agent conversations.

The Runner coordinates persistence around the message-driven Agent Loop. It
does not implement model decisions, tool execution, SQLite serialization, or
transport-specific request handling.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from superhp_agent.agents import BookRecommendationAgent
from superhp_agent.contracts import (
    RecommendationAgentPhase,
    RecommendationAgentReply,
    RecommendationAgentSession,
    RecommendationRequest,
)
from superhp_agent.ports import RecommendationSessionRepository


class RecommendationSessionNotFoundError(LookupError):
    """Raised when a caller tries to resume an unknown conversation."""


class RecommendationAgentRunner:
    """Load, advance, and save recommendation sessions as one use case."""

    def __init__(
        self,
        agent_factory: Callable[[], BookRecommendationAgent],
        session_repository: RecommendationSessionRepository,
    ):
        self.agent_factory = agent_factory
        self.session_repository = session_repository
        self._agent: BookRecommendationAgent | None = None

    async def start(
        self,
        request: RecommendationRequest,
        *,
        session_id: str | None = None,
    ) -> RecommendationAgentReply:
        """Create a durable session and advance it to its first pause."""
        session = self.agent.start(request, session_id=session_id)
        self.session_repository.save(session)
        reply = await self.agent.run(session)
        self.session_repository.save(reply.session)
        return reply

    async def resume(
        self,
        session_id: str,
        *,
        user_message: str,
    ) -> RecommendationAgentReply:
        """Restore one session, accept the next user message, and persist it."""
        session = self.session_repository.load(session_id)
        if session is None:
            raise RecommendationSessionNotFoundError(
                f"recommendation session not found: {session_id}"
            )
        reply = await self.agent.run(session, user_message=user_message)
        self.session_repository.save(reply.session)
        return reply

    async def handoff(
        self,
        request: RecommendationRequest,
        *,
        session_id: str | None = None,
        user_message: str,
    ) -> RecommendationAgentReply:
        """Start a difficulty turn, retaining a prior visible conversation."""
        session = (
            self.session_repository.load(session_id)
            if session_id
            else None
        )
        if session is None:
            session = self.agent.start(request)
        else:
            context_start_index = len(session.conversation)
            session = replace(
                session,
                request=request,
                phase=RecommendationAgentPhase.COLLECTING_PREFERENCES,
                tool_call_count=0,
                observed_catalog_ids=(),
                recommended_catalog_ids=(),
                selected_catalog_id="",
                context_start_index=context_start_index,
                error_code="",
            )
        self.session_repository.save(session)
        reply = await self.agent.run(
            session,
            user_message=user_message,
        )
        self.session_repository.save(reply.session)
        return reply

    def load(self, session_id: str) -> RecommendationAgentSession | None:
        """Expose stored state to a future HTTP or WebSocket transport."""
        return self.session_repository.load(session_id)

    @property
    def agent(self) -> BookRecommendationAgent:
        """Create the Provider-backed Agent only when the use case is invoked."""
        if self._agent is None:
            self._agent = self.agent_factory()
        return self._agent
