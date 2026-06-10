from pathlib import Path

from superhp_agent.corpus import CorpusStore
from superhp_agent.services.annotator import VocabItem
from superhp_agent.storage import AppDB


def write_unit(root: Path):
    path = root / "hp01" / "ch01" / "01.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """---
id: hp01-ch01
chapter_id: hp01-ch01
book_id: hp01
book_title: "Harry Potter and the Philosopher's Stone"
chapter_no: 1
chapter_title: "The Boy Who Lived"
summary: "Summary"
---

Body text.
""",
        encoding="utf-8",
    )


def test_add_and_list_vocabulary_by_unit_and_chapter(tmp_path):
    corpus_root = tmp_path / "corpus"
    write_unit(corpus_root)
    unit = CorpusStore(corpus_root).get_unit("hp01-ch01").meta
    db = AppDB(tmp_path / "app.sqlite3")

    inserted = db.add_vocabulary_items(
        unit,
        [VocabItem(word="wand", translation="魔杖", context="a wand")],
    )

    assert inserted == 1
    assert db.count_vocabulary_for_unit("hp01-ch01") == 1
    by_unit = db.list_vocabulary(unit_id="hp01-ch01")
    by_chapter = db.list_vocabulary(chapter_id="hp01-ch01")
    assert by_unit[0]["word"] == "wand"
    assert by_unit[0]["translation"] == "魔杖"
    assert by_chapter[0]["unit_id"] == "hp01-ch01"


def test_add_vocabulary_is_idempotent_per_unit(tmp_path):
    corpus_root = tmp_path / "corpus"
    write_unit(corpus_root)
    unit = CorpusStore(corpus_root).get_unit("hp01-ch01").meta
    db = AppDB(tmp_path / "app.sqlite3")

    db.add_vocabulary_items(unit, [VocabItem(word="wand", translation="魔杖", context="first")])
    db.add_vocabulary_items(unit, [VocabItem(word="wand", translation="魔杖", context="second")])

    rows = db.list_vocabulary(unit_id="hp01-ch01")
    assert len(rows) == 1
    assert rows[0]["encounter_count"] == 2
    assert rows[0]["context"] == "second"


def test_manual_vocabulary_can_be_mastered_and_deleted(tmp_path):
    corpus_root = tmp_path / "corpus"
    write_unit(corpus_root)
    unit = CorpusStore(corpus_root).get_unit("hp01-ch01").meta
    db = AppDB(tmp_path / "app.sqlite3")

    vocab_id = db.add_manual_vocabulary(
        unit,
        word="crutches",
        translation="拐杖",
        context="He had crutches.",
        pos="noun",
    )

    rows = db.list_vocabulary(unit_id="hp01-ch01")
    assert rows[0]["id"] == vocab_id
    assert rows[0]["word"] == "crutches"
    assert rows[0]["pos"] == "noun"
    assert rows[0]["mastered"] == 0

    assert db.set_mastered_by_word("CRUTCHES", True)
    assert db.list_vocabulary(unit_id="hp01-ch01")[0]["mastered"] == 1
    assert db.count_vocabulary_for_unit("hp01-ch01") == 0

    assert db.set_mastered(vocab_id, False)
    assert db.list_vocabulary(unit_id="hp01-ch01")[0]["mastered"] == 0
    assert db.count_vocabulary_for_unit("hp01-ch01") == 1

    assert db.delete_vocabulary(vocab_id)
    assert db.list_vocabulary(unit_id="hp01-ch01") == []


def test_vocabulary_context_strips_annotation_markers(tmp_path):
    corpus_root = tmp_path / "corpus"
    write_unit(corpus_root)
    unit = CorpusStore(corpus_root).get_unit("hp01-ch01").meta
    db = AppDB(tmp_path / "app.sqlite3")

    db.add_manual_vocabulary(
        unit,
        word="exasperated",
        translation="恼怒的",
        context="half-[[exasperated|恼怒的]], half-[[admiring|钦佩的]].",
    )

    rows = db.list_vocabulary(unit_id="hp01-ch01")
    assert rows[0]["context"] == "half-exasperated, half-admiring."
