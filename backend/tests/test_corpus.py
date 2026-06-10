from pathlib import Path

import pytest

from superhp_agent.corpus import CorpusError, CorpusStore


def write_unit(root: Path, rel: str, unit_id: str, *, section_no: int = 1):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""---
id: {unit_id}
chapter_id: hp01-ch01
book_id: hp01
book_title: "Harry Potter and the Philosopher's Stone"
chapter_no: 1
chapter_title: "The Boy Who Lived"
section_no: {section_no}
section_count: 2
summary: 示例摘要
---

Body text.
""",
        encoding="utf-8",
    )


def test_lists_units_from_frontmatter(tmp_path):
    write_unit(tmp_path, "hp01/ch01/01.md", "hp01-ch01-sec01")
    store = CorpusStore(tmp_path)

    units = store.list_units()

    assert len(units) == 1
    assert units[0].id == "hp01-ch01-sec01"
    assert units[0].chapter_id == "hp01-ch01"
    assert units[0].section_no == 1
    assert units[0].section_count == 2
    assert units[0].summary == "示例摘要"


def test_get_unit_body(tmp_path):
    write_unit(tmp_path, "hp01/ch01/01.md", "hp01-ch01-sec01")
    store = CorpusStore(tmp_path)

    doc = store.get_unit("hp01-ch01-sec01")

    assert doc.meta.chapter_title == "The Boy Who Lived"
    assert doc.body == "Body text."


def test_duplicate_unit_id_fails(tmp_path):
    write_unit(tmp_path, "hp01/ch01/a.md", "hp01-ch01-sec01")
    write_unit(tmp_path, "hp01/ch01/b.md", "hp01-ch01-sec01")
    store = CorpusStore(tmp_path)

    with pytest.raises(CorpusError):
        store.list_units()


def test_units_sort_by_section_number(tmp_path):
    write_unit(tmp_path, "hp01/ch01/02.md", "hp01-ch01-sec02", section_no=2)
    write_unit(tmp_path, "hp01/ch01/01.md", "hp01-ch01-sec01", section_no=1)
    store = CorpusStore(tmp_path)

    units = store.list_units()

    assert [unit.id for unit in units] == ["hp01-ch01-sec01", "hp01-ch01-sec02"]