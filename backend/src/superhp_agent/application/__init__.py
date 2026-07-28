"""Application composition and use-case orchestration boundaries."""

from superhp_agent.application.chapter_checkpoints import ChapterCheckpointRecorder
from superhp_agent.application.container import AppContainer, build_container
from superhp_agent.application.difficulty_handoff import (
    DifficultyHandoffBookNotFoundError,
    DifficultyRecommendationHandoffBuilder,
)
from superhp_agent.application.reading_adaptation import (
    ReadingAdaptationAction,
    ReadingAdaptationDecision,
    ReadingAdaptationPolicy,
    ReadingAdaptationState,
)
from superhp_agent.application.reading_adaptation_evaluator import (
    ReadingAdaptationEvaluation,
    ReadingAdaptationEvaluator,
    ReadingAdaptationWindow,
)
from superhp_agent.application.reading_difficulty_prompts import (
    ReadingDifficultyPromptCoordinator,
)
from superhp_agent.application.reading_monitor import (
    ReadingDifficultyMonitor,
    ReadingDifficultyPolicy,
)
from superhp_agent.application.recommendation_companion import (
    RecommendationCompanionProjection,
    RecommendationCompanionProjectionError,
    legacy_recommendation_episode_id,
    legacy_recommendation_message_id,
    project_recommendation_session,
)
from superhp_agent.application.recommendation_runner import (
    RecommendationAgentRunner,
    RecommendationSessionNotFoundError,
)

__all__ = [
    "AppContainer",
    "ChapterCheckpointRecorder",
    "DifficultyHandoffBookNotFoundError",
    "DifficultyRecommendationHandoffBuilder",
    "ReadingAdaptationAction",
    "ReadingAdaptationDecision",
    "ReadingAdaptationEvaluation",
    "ReadingAdaptationEvaluator",
    "ReadingAdaptationPolicy",
    "ReadingAdaptationState",
    "ReadingAdaptationWindow",
    "ReadingDifficultyMonitor",
    "ReadingDifficultyPolicy",
    "ReadingDifficultyPromptCoordinator",
    "RecommendationAgentRunner",
    "RecommendationCompanionProjection",
    "RecommendationCompanionProjectionError",
    "RecommendationSessionNotFoundError",
    "build_container",
    "legacy_recommendation_episode_id",
    "legacy_recommendation_message_id",
    "project_recommendation_session",
]
