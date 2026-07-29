"""Application composition and use-case orchestration boundaries."""

from superhp_agent.application.chapter_checkpoints import ChapterCheckpointRecorder
from superhp_agent.application.container import AppContainer, build_container
from superhp_agent.application.difficulty_handoff import (
    DifficultyHandoffBookNotFoundError,
    DifficultyRecommendationHandoffBuilder,
)
from superhp_agent.application.manual_reading_companion import (
    ManualReadingCompanionError,
    ManualReadingCompanionRunner,
)
from superhp_agent.application.previous_chapter_search import (
    PreviousChapterSearchError,
    PreviousChapterSearchPolicy,
    PreviousChapterSearchService,
)
from superhp_agent.application.previous_reading_scope import (
    PreviousReadingScopeBuilder,
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
from superhp_agent.application.reading_companion_sessions import (
    ReadingCompanionSessionConflictError,
    ReadingCompanionSessionCoordinator,
    ReadingCompanionSessionNotFoundError,
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
from superhp_agent.application.recommendation_episode import (
    RecommendationEpisodeReply,
    RecommendationEpisodeRunner,
)
from superhp_agent.application.recommendation_runner import (
    RecommendationAgentRunner,
    RecommendationSessionNotFoundError,
)
from superhp_agent.application.vocabulary_history_search import (
    VocabularyHistorySearchError,
    VocabularyHistorySearchService,
)

__all__ = [
    "AppContainer",
    "ChapterCheckpointRecorder",
    "DifficultyHandoffBookNotFoundError",
    "DifficultyRecommendationHandoffBuilder",
    "ManualReadingCompanionError",
    "ManualReadingCompanionRunner",
    "ReadingCompanionSessionCoordinator",
    "PreviousChapterSearchError",
    "PreviousChapterSearchPolicy",
    "PreviousChapterSearchService",
    "PreviousReadingScopeBuilder",
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
    "ReadingCompanionSessionConflictError",
    "ReadingCompanionSessionNotFoundError",
    "RecommendationAgentRunner",
    "RecommendationCompanionProjection",
    "RecommendationCompanionProjectionError",
    "RecommendationEpisodeReply",
    "RecommendationEpisodeRunner",
    "RecommendationSessionNotFoundError",
    "VocabularyHistorySearchError",
    "VocabularyHistorySearchService",
    "build_container",
    "legacy_recommendation_episode_id",
    "legacy_recommendation_message_id",
    "project_recommendation_session",
]
