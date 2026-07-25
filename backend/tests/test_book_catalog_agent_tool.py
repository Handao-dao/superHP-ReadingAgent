"""Tests for the SDK-neutral Agent tool around local book matching."""

import json

import pytest

from superhp_agent.agent_tools import BookCatalogSearchTool
from superhp_agent.contracts import (
    BookCandidate,
    BookDifficulty,
    BookEntryKind,
    BookSearchQuery,
)
from superhp_agent.services import RecommendationCandidateService


class ToolCatalog:
    def __init__(self):
        self.query = None

    async def find_by_id(self, catalog_id: str):
        return None

    async def search_books(self, query: BookSearchQuery):
        self.query = query
        return [
            BookCandidate(
                catalog_id="cam-jansen",
                title_en="Cam Jansen",
                title_zh="照相机女孩",
                author="David A. Adler",
                difficulty=BookDifficulty(330, 550),
                entry_kind=BookEntryKind.SERIES,
                genres=("mystery", "school_life"),
            )
        ]


@pytest.mark.asyncio
async def test_tool_normalizes_primitive_inputs_and_returns_json_ready_evidence():
    catalog = ToolCatalog()
    tool = BookCatalogSearchTool(RecommendationCandidateService(catalog))

    result = await tool.run(
        lexile_min=300,
        lexile_max=500,
        genres=[" Mystery ", "MYSTERY", "school_life"],
        entry_kinds=[" SERIES "],
        excluded_ids=["already-read", "ALREADY-READ"],
        limit=3,
    )

    assert result["tool"] == "search_local_book_catalog"
    assert result["match_mode"] == "strict"
    assert result["found"] is True
    assert result["result_count"] == 1
    assert result["criteria"] == {
        "lexile_min": 300,
        "lexile_max": 500,
        "genres": ["mystery", "school_life"],
        "entry_kinds": ["series"],
        "excluded_ids": ["already-read"],
        "limit": 3,
    }
    assert result["candidates"][0] == {
        "rank": 1,
        "catalog_id": "cam-jansen",
        "title_en": "Cam Jansen",
        "title_zh": "照相机女孩",
        "author": "David A. Adler",
        "entry_kind": "series",
        "lexile_min": 330,
        "lexile_max": 550,
        "genres": ["mystery", "school_life"],
        "matched_genres": ["mystery", "school_life"],
        "difficulty_distance": 40,
    }
    assert json.loads(json.dumps(result, ensure_ascii=False)) == result
    assert catalog.query is not None
    assert catalog.query.limit == 100


@pytest.mark.asyncio
async def test_tool_requires_a_meaningful_matching_criterion():
    tool = BookCatalogSearchTool(RecommendationCandidateService(ToolCatalog()))

    with pytest.raises(ValueError, match="at least one Lexile bound or genre"):
        await tool.run()


@pytest.mark.asyncio
async def test_tool_accepts_one_genre_string_as_one_value():
    tool = BookCatalogSearchTool(RecommendationCandidateService(ToolCatalog()))

    result = await tool.run(genres="Mystery")

    assert result["criteria"]["genres"] == ["mystery"]


@pytest.mark.asyncio
async def test_tool_returns_an_explicit_empty_strict_result():
    tool = BookCatalogSearchTool(RecommendationCandidateService(ToolCatalog()))

    result = await tool.run(genres=["fantasy"])

    assert result["found"] is False
    assert result["result_count"] == 0
    assert result["candidates"] == []


@pytest.mark.asyncio
async def test_tool_rejects_unknown_entry_kind_before_querying_catalog():
    catalog = ToolCatalog()
    tool = BookCatalogSearchTool(RecommendationCandidateService(catalog))

    with pytest.raises(ValueError, match="unknown entry kind"):
        await tool.run(genres=["mystery"], entry_kinds=["volume"])

    assert catalog.query is None
