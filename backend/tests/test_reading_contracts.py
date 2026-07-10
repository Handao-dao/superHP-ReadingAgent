"""Compatibility tests for extracted read-only reading contracts."""

from superhp_agent.contracts import AgentCard, ReadingUnitDetail, ReadingUnitMeta
from superhp_agent.schemas import (
    AgentCard as LegacyAgentCard,
)
from superhp_agent.schemas import (
    ChapterDetail,
    ChapterMeta,
)
from superhp_agent.schemas import (
    ReadingUnitDetail as LegacyReadingUnitDetail,
)
from superhp_agent.schemas import (
    ReadingUnitMeta as LegacyReadingUnitMeta,
)


def test_reading_contracts_keep_legacy_imports():
    assert LegacyReadingUnitMeta is ReadingUnitMeta
    assert LegacyReadingUnitDetail is ReadingUnitDetail
    assert LegacyAgentCard is AgentCard
    assert ChapterMeta is ReadingUnitMeta
    assert ChapterDetail is ReadingUnitDetail


def test_reading_contracts_keep_json_shape():
    meta = ReadingUnitMeta(
        id="hp01-ch01",
        chapter_id="hp01-ch01",
        book_id="hp01",
        book_title="Harry Potter",
        chapter_no=1,
        chapter_title="The Boy Who Lived",
    )
    detail = ReadingUnitDetail(meta=meta, body="Body text.", body_kind="source")
    card = AgentCard(id="unit-hp01-ch01", type="reading", title="Start", body="Ready")

    assert detail.model_dump()["meta"]["status"] == "unread"
    assert detail.model_dump()["body_kind"] == "source"
    assert card.model_dump()["actions"] == []
