"""Contract tests for conversational recommendation result tools."""

import pytest

from superhp_agent.agent_tools import (
    PresentBookRecommendationsTool,
    SelectRecommendedBookTool,
)


@pytest.mark.asyncio
async def test_present_tool_pauses_without_terminating():
    result = await PresentBookRecommendationsTool().run(
        catalog_ids=["cam-jansen", "nate-the-great"],
        message="这两本都适合作为起点。",
    )

    assert result == {
        "action": "present_recommendations",
        "catalog_ids": ["cam-jansen", "nate-the-great"],
        "message": "这两本都适合作为起点。",
    }


@pytest.mark.asyncio
async def test_select_tool_returns_explicit_terminal_choice():
    result = await SelectRecommendedBookTool().run(
        catalog_id="cam-jansen",
        message="已经确认这本书。",
    )

    assert result == {
        "action": "select_recommended_book",
        "terminate": True,
        "catalog_id": "cam-jansen",
        "message": "已经确认这本书。",
    }


@pytest.mark.asyncio
async def test_result_tools_reject_blank_or_duplicate_values():
    with pytest.raises(ValueError, match="unique"):
        await PresentBookRecommendationsTool().run(
            catalog_ids=["same", "same"],
            message="重复候选。",
        )
    with pytest.raises(ValueError, match="must not be empty"):
        await SelectRecommendedBookTool().run(
            catalog_id=" ",
            message="选择。",
        )
