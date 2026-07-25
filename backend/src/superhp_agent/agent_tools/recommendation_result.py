"""Terminal tool for returning verified book recommendations.

The tool validates the model-facing payload only. The Agent loop still owns
catalog provenance checks because only the current session knows which ids
were actually observed.
"""

from __future__ import annotations

from collections.abc import Iterable


class PresentBookRecommendationsTool:
    """Finish recommendation with one to three catalog-backed candidates."""

    name = "present_book_recommendations"
    description = (
        "Finish the recommendation task with 1 to 3 catalog ids already returned "
        "by search_local_book_catalog and a concise user-facing explanation."
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
        """Return a terminal result after validating its stable payload."""
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
            "terminate": True,
            "catalog_ids": list(normalized_ids),
            "message": message.strip(),
        }
