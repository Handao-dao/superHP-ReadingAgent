"""Boundary test for the provider-neutral recommendation Agent model Port."""

from superhp_agent.contracts import (
    RecommendationAgentDecision,
    RecommendationAgentDecisionKind,
)
from superhp_agent.ports import RecommendationAgentModel


class MinimalRecommendationModel:
    async def decide(self, observation):
        return RecommendationAgentDecision(
            kind=RecommendationAgentDecisionKind.ASK_USER,
            message="你喜欢哪类故事？",
        )


def test_minimal_recommendation_model_satisfies_port():
    assert isinstance(MinimalRecommendationModel(), RecommendationAgentModel)
