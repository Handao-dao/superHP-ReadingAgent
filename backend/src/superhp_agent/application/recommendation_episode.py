"""Run recommendation work as one specialized Companion Episode.

This migration boundary reuses the existing recommendation Agent, Context
Builder, Provider, and ToolRegistry. Recommendation-only phase and candidate
state remain specialized; Session, Episode, and Message views are projected
through the shared companion contracts for future unified persistence.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from superhp_agent.agents import BookRecommendationAgent
from superhp_agent.application.recommendation_companion import (
    RecommendationCompanionProjection,
    project_recommendation_session,
)
from superhp_agent.contracts import (
    RecommendationAgentPhase,
    RecommendationAgentReply,
    RecommendationAgentSession,
    RecommendationRequest,
)


@dataclass(frozen=True)
class RecommendationEpisodeReply:
    """Specialized recommendation result with a common companion projection."""

    recommendation: RecommendationAgentReply
    companion: RecommendationCompanionProjection

    @property
    def message(self) -> str:
        """Expose the visible assistant text without duplicating state."""
        return self.recommendation.message


class RecommendationEpisodeRunner:
    """Advance one recommendation task and project its current Episode."""

    def __init__(
        self,
        agent_factory: Callable[[], BookRecommendationAgent],
        *,
        reader_key: str = "default",
    ):
        if not reader_key.strip():
            raise ValueError("reader_key must not be empty")
        self.agent_factory = agent_factory
        self.reader_key = reader_key.strip()
        self._agent: BookRecommendationAgent | None = None

    async def start(
        self,
        request: RecommendationRequest,
        *,
        session_id: str | None = None,
    ) -> RecommendationEpisodeReply:
        """Open and advance an onboarding or requested recommendation."""
        session = self.agent.start(request, session_id=session_id)
        return self._project(await self.agent.run(session))

    async def resume(
        self,
        session: RecommendationAgentSession,
        *,
        user_message: str,
    ) -> RecommendationEpisodeReply:
        """Continue one paused recommendation Episode in memory."""
        return self._project(
            await self.agent.run(session, user_message=user_message)
        )

    async def retry(
        self,
        session: RecommendationAgentSession,
    ) -> RecommendationEpisodeReply:
        """Retry the pending model turn without duplicating user content."""
        return self._project(await self.agent.run(session))

    async def handoff(
        self,
        request: RecommendationRequest,
        *,
        user_message: str,
        previous: RecommendationAgentSession | None = None,
        session_id: str | None = None,
    ) -> RecommendationEpisodeReply:
        """Open a new recommendation Episode while retaining prior history."""
        if previous is None:
            session = self.agent.start(request, session_id=session_id)
        else:
            if session_id is not None and session_id != previous.session_id:
                raise ValueError(
                    "session_id must match the previous recommendation session"
                )
            session = replace(
                previous,
                request=request,
                phase=RecommendationAgentPhase.COLLECTING_PREFERENCES,
                tool_call_count=0,
                observed_catalog_ids=(),
                recommended_catalog_ids=(),
                selected_catalog_id="",
                context_start_index=len(previous.conversation),
                error_code="",
            )
        return self._project(
            await self.agent.run(session, user_message=user_message)
        )

    def _project(
        self,
        reply: RecommendationAgentReply,
    ) -> RecommendationEpisodeReply:
        return RecommendationEpisodeReply(
            recommendation=reply,
            companion=project_recommendation_session(
                reply.session,
                reader_key=self.reader_key,
            ),
        )

    @property
    def agent(self) -> BookRecommendationAgent:
        """Create the Provider-backed specialized Agent only when invoked."""
        if self._agent is None:
            self._agent = self.agent_factory()
        return self._agent
