"""Narrow, SDK-neutral tools that may be exposed to a future Agent loop.

Agent tools translate model-friendly primitive inputs into application calls.
They do not replace Ports, contain SQL, or own recommendation policy.
"""

from superhp_agent.agent_tools.book_catalog import BookCatalogSearchTool
from superhp_agent.agent_tools.reading_history import (
    PreviousChapterSearchTool,
    VocabularyHistorySearchTool,
)
from superhp_agent.agent_tools.recommendation_result import (
    PresentBookRecommendationsTool,
    SelectRecommendedBookTool,
)
from superhp_agent.agent_tools.registry import (
    AgentTool,
    AgentToolNotAllowedError,
    ToolRegistry,
    UnknownAgentToolError,
)

__all__ = [
    "AgentTool",
    "AgentToolNotAllowedError",
    "BookCatalogSearchTool",
    "PresentBookRecommendationsTool",
    "PreviousChapterSearchTool",
    "SelectRecommendedBookTool",
    "ToolRegistry",
    "UnknownAgentToolError",
    "VocabularyHistorySearchTool",
]
