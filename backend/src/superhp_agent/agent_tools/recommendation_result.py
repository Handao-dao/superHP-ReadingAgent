"""Tools for presenting candidates and confirming one conversational choice.

These tools validate model-facing payloads only. The Agent loop still owns
catalog provenance checks because only the current session knows which ids
were observed and which candidates were actually presented to the user.
"""

from __future__ import annotations

from collections.abc import Iterable


class PresentBookRecommendationsTool:
    """Present one to three candidates without ending the conversation."""

    name = "present_book_recommendations"
    description = (
        "Present 1 to 3 catalog ids already returned by "
        "search_local_book_catalog, explain them concisely, and then wait for "
        "the user's natural-language feedback."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "catalog_ids": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 3,
            },
            "message": {"type": "string", "minLength": 1},
        },
        "required": ["catalog_ids", "message"],
        "additionalProperties": False,
    }

    async def run(
        self,
        *,
        catalog_ids: Iterable[str],
        message: str,
    ) -> dict[str, object]:
        """Return a pause result after validating its stable payload."""
        if isinstance(catalog_ids, str):
            raise ValueError("catalog_ids must be an array")
        normalized_ids = tuple(
            catalog_id.strip()
            for catalog_id in catalog_ids
            if isinstance(catalog_id, str) and catalog_id.strip()
        )
        if not 1 <= len(normalized_ids) <= 3:
            raise ValueError("catalog_ids must contain between 1 and 3 ids")
        if len(set(normalized_ids)) != len(normalized_ids):
            raise ValueError("catalog_ids must be unique")
        if not message.strip():
            raise ValueError("message must not be empty")
        return {
            "action": "present_recommendations",
            "catalog_ids": list(normalized_ids),
            "message": message.strip(),
        }


class SelectRecommendedBookTool:
    """Confirm one previously presented candidate and finish the task."""

    name = "select_recommended_book"
    description = (
        "Confirm one previously presented catalog id only after the user "
        "clearly chooses it, then finish the recommendation conversation."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "catalog_id": {"type": "string", "minLength": 1},
            "message": {"type": "string", "minLength": 1},
        },
        "required": ["catalog_id", "message"],
        "additionalProperties": False,
    }

    async def run(
        self,
        *,
        catalog_id: str,
        message: str,
    ) -> dict[str, object]:
        """Return a terminal selection for Loop-level provenance checks."""
        normalized_id = catalog_id.strip()
        if not normalized_id:
            raise ValueError("catalog_id must not be empty")
        if not message.strip():
            raise ValueError("message must not be empty")
        return {
            "action": "select_recommended_book",
            "terminate": True,
            "catalog_id": normalized_id,
            "message": message.strip(),
        }
