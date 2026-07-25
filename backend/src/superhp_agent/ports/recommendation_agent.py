"""Model capability required by the book-recommendation Agent loop.

The Port returns one normalized decision at a time. A future adapter may use
native function calling or validated JSON, but the loop does not depend on
either provider protocol.
"""

from typing import Protocol, runtime_checkable

from superhp_agent.contracts import (
    RecommendationAgentDecision,
    RecommendationAgentObservation,
)


@runtime_checkable
class RecommendationAgentModel(Protocol):
    """Choose the next bounded action from the current Agent observation."""

    async def decide(
        self,
        observation: RecommendationAgentObservation,
    ) -> RecommendationAgentDecision: ...
