import hashlib
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


def test_store_writes_and_reads_canonical_copy(tmp_path):
    corpus_root = tmp_path / "corpus"
    write_unit(corpus_root)
    document = CorpusStore(corpus_root).get_unit("hp01-ch01")
    store = AnnotatedCopyStore(tmp_path / "annotated")

    path = store.write(
        document,
        annotated_text="Body [[text|文本|noun]].",
        vocabulary=[AnnotationItem(word="text", translation="文本", context="Body text.")],
        status="degraded",
        validated_chunk_count=1,
        total_chunk_count=2,
    )
    copy = store.read("hp01-ch01")

    assert path.name == "hp01-ch01.annotated.md"
    assert copy is not None
    assert copy.path == path
    assert "<!-- extracted_vocabulary" in copy.body
    assert copy.body.endswith("Body [[text|文本|noun]].")
    assert "level:" not in copy.metadata
    source_hash = hashlib.sha256(document.body.encode("utf-8")).hexdigest()
    assert f"source_hash: {source_hash}" in copy.metadata
    assert "annotation_format_version: 1" in copy.metadata
    assert "status: degraded" in copy.metadata
    assert "validated_chunk_count: 1" in copy.metadata
    assert "total_chunk_count: 2" in copy.metadata
    assert "# - text: 文本 (other)" in path.read_text(encoding="utf-8")
    assert store.exists_any("hp01-ch01") is True


def test_store_keeps_existing_copy_when_atomic_replace_fails(tmp_path, monkeypatch):
    corpus_root = tmp_path / "corpus"
    write_unit(corpus_root)
    document = CorpusStore(corpus_root).get_unit("hp01-ch01")
    store = AnnotatedCopyStore(tmp_path / "annotated")
    path = store.path_for("hp01-ch01")
    path.parent.mkdir(parents=True)
    path.write_text("existing copy", encoding="utf-8")

    def fail_replace(self, target):
        raise OSError("replace failed")

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        store.write(
            document,
            annotated_text="Body [[text|文本|noun]].",
            vocabulary=[],
        )

    assert path.read_text(encoding="utf-8") == "existing copy"
    assert list(path.parent.glob("*.tmp")) == []


def test_store_reads_canonical_copy(tmp_path):
    root = tmp_path / "annotated"
    root.mkdir()
    legacy = root / "hp01-ch01.annotated.md"
    legacy.write_text("---\nbody_kind: annotated\n---\n\nLegacy body.\n", encoding="utf-8")
    store = AnnotatedCopyStore(root)

    copy = store.read("hp01-ch01")

    assert copy is not None
    assert copy.path == legacy
    assert copy.body == "Legacy body."


@pytest.mark.parametrize("unit_id", ["", "..", "../outside", "folder/unit"])
def test_store_rejects_unsafe_unit_ids(tmp_path, unit_id):
    store = AnnotatedCopyStore(tmp_path / "annotated")

    with pytest.raises(ValueError):
        store.path_for(unit_id)
