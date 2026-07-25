"""Application composition and use-case orchestration boundaries."""

from superhp_agent.application.container import AppContainer, build_container
from superhp_agent.application.recommendation_runner import (
    RecommendationAgentRunner,
    RecommendationSessionNotFoundError,
)

__all__ = [
    "AppContainer",
    "RecommendationAgentRunner",
    "RecommendationSessionNotFoundError",
    "build_container",
]
