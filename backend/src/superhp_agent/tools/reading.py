"""Reading-domain tools used by guided actions."""

from __future__ import annotations

from typing import Any

from superhp_agent.corpus import CorpusStore
from superhp_agent.tools.base import Tool


class ListReadingUnitsTool(Tool):
    name = "list_reading_units"
    description = "List reading units from the local corpus."

    def __init__(self, corpus: CorpusStore):
        self.corpus = corpus

    async def execute(self, **kwargs: Any) -> list[dict]:
        return [unit.__dict__ | {"path": str(unit.path)} for unit in self.corpus.list_units()]


class GetReadingUnitTool(Tool):
    name = "get_reading_unit"
    description = "Read one reading unit by id from the local corpus."

    def __init__(self, corpus: CorpusStore):
        self.corpus = corpus

    async def execute(self, **kwargs: Any) -> dict:
        unit_id = str(kwargs.get("unit_id") or kwargs.get("chapter_id") or "")
        doc = self.corpus.get_unit(unit_id)
        return {"meta": doc.meta.__dict__ | {"path": str(doc.meta.path)}, "body": doc.body}


class ListChaptersTool(ListReadingUnitsTool):
    name = "list_chapters"
    description = "Compatibility alias for list_reading_units."


class GetChapterTool(GetReadingUnitTool):
    name = "get_chapter"
    description = "Compatibility alias for get_reading_unit."