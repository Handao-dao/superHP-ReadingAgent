"""Persistence capability for resumable book-recommendation conversations.

The Port stores the complete Agent session aggregate. It does not know how the
Agent advances the conversation or how a concrete database serializes it.
"""

from typing import Protocol, runtime_checkable

from superhp_agent.contracts.recommendation import RecommendationAgentSession


@runtime_checkable
class RecommendationSessionRepository(Protocol):
    """Save, restore, and remove one recommendation conversation by id."""

    def save(self, session: RecommendationAgentSession) -> None: ...

    def load(self, session_id: str) -> RecommendationAgentSession | None: ...

    def delete(self, session_id: str) -> bool: ...
