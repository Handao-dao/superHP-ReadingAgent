"""Stable data contracts exchanged across backend boundaries."""

from superhp_agent.contracts.actions import AgentAction
from superhp_agent.contracts.annotation import (
    AnnotationChunkOutcome,
    AnnotationItem,
    AnnotationResult,
    ServiceIssue,
)
from superhp_agent.contracts.events import BackendEvent
from superhp_agent.contracts.llm import LLMResponse
from superhp_agent.contracts.reading import (
    AgentCard,
    ReadingProgressSnapshot,
    ReadingUnitDetail,
    ReadingUnitMeta,
)
from superhp_agent.contracts.recommendation import (
    BookCandidate,
    BookCandidateMatch,
    BookCandidateMatchResult,
    BookDifficulty,
    BookEntryKind,
    BookRecommendationHandoff,
    BookSearchQuery,
    BookSnapshot,
    OperationalReadingBand,
    ReadingDifficultyEvidence,
    ReadingPreference,
    RecommendationOrigin,
    RecommendationOutcome,
    RecommendationOutcomeKind,
    RecommendationRequest,
)

__all__ = [
    "AgentAction",
    "AgentCard",
    "AnnotationChunkOutcome",
    "AnnotationItem",
    "AnnotationResult",
    "BackendEvent",
    "BookCandidate",
    "BookCandidateMatch",
    "BookCandidateMatchResult",
    "BookDifficulty",
    "BookEntryKind",
    "BookRecommendationHandoff",
    "BookSearchQuery",
    "BookSnapshot",
    "LLMResponse",
    "OperationalReadingBand",
    "ReadingDifficultyEvidence",
    "ReadingPreference",
    "ReadingUnitDetail",
    "ReadingUnitMeta",
    "ReadingProgressSnapshot",
    "RecommendationOrigin",
    "RecommendationOutcome",
    "RecommendationOutcomeKind",
    "RecommendationRequest",
    "ServiceIssue",
]
