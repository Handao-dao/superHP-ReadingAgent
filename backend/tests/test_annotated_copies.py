from pathlib import Path

import pytest

from superhp_agent.artifacts import AnnotatedCopyStore
from superhp_agent.corpus import CorpusStore
from superhp_agent.profiles import AnnotationItem


def write_unit(root: Path) -> None:
    path = root / "hp01" / "hp01-ch01.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """---
id: hp01-ch01
chapter_id: hp01-ch01
book_id: hp01
book_title: "Harry Potter and the Philosopher's Stone"
chapter_no: 1
chapter_title: "The Boy Who Lived"
profile_id: english_novel
---

Body text.
""",
        encoding="utf-8",
    )


def test_store_writes_and_reads_density_copy(tmp_path):
    corpus_root = tmp_path / "corpus"
    write_unit(corpus_root)
    document = CorpusStore(corpus_root).get_unit("hp01-ch01")
    store = AnnotatedCopyStore(tmp_path / "annotated")

    path = store.write(
        document,
        annotated_text="Body [[text|文本]].",
        vocabulary=[AnnotationItem(word="text", translation="文本", context="Body text.")],
        level="advanced",
    )
    copy = store.read("hp01-ch01", "advanced")

    assert path.name == "hp01-ch01.advanced.annotated.md"
    assert copy is not None
    assert copy.path == path
    assert "<!-- extracted_vocabulary" in copy.body
    assert copy.body.endswith("Body [[text|文本]].")
    assert "level: advanced" in copy.metadata
    assert "# - text: 文本 (other)" in path.read_text(encoding="utf-8")
    assert store.exists_any("hp01-ch01") is True


def test_store_uses_legacy_copy_only_for_intermediate(tmp_path):
    root = tmp_path / "annotated"
    root.mkdir()
    legacy = root / "hp01-ch01.annotated.md"
    legacy.write_text("---\nbody_kind: annotated\n---\n\nLegacy body.\n", encoding="utf-8")
    store = AnnotatedCopyStore(root)

    intermediate = store.read("hp01-ch01", "intermediate")

    assert intermediate is not None
    assert intermediate.path == legacy
    assert intermediate.body == "Legacy body."
    assert store.read("hp01-ch01", "advanced") is None


@pytest.mark.parametrize("unit_id", ["", "..", "../outside", "folder/unit"])
def test_store_rejects_unsafe_unit_ids(tmp_path, unit_id):
    store = AnnotatedCopyStore(tmp_path / "annotated")

    with pytest.raises(ValueError):
        store.path_for(unit_id, "intermediate")
