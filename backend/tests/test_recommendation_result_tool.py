"""Tests for the non-terminal recommendation presentation tool."""

import pytest

from superhp_agent.agent_tools import PresentBookRecommendationsTool


@pytest.mark.asyncio
async def test_presentation_tool_returns_one_to_three_unique_ids():
    tool = PresentBookRecommendationsTool()

    result = await tool.run(
        catalog_ids=["cam-jansen", "nate-the-great"],
        message="这两本适合作为起点。",
    )

    assert result == {
        "action": "present_recommendations",
        "catalog_ids": ["cam-jansen", "nate-the-great"],
        "message": "这两本适合作为起点。",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "catalog_ids",
    [
        [],
        ["a", "a"],
        ["a", "b", "c", "d"],
        "abc",
    ],
)
async def test_presentation_tool_rejects_invalid_candidate_ids(catalog_ids):
    tool = PresentBookRecommendationsTool()

    with pytest.raises(ValueError):
        await tool.run(catalog_ids=catalog_ids, message="推荐")
