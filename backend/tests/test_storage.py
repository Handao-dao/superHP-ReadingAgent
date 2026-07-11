from pathlib import Path

from superhp_agent.corpus import CorpusStore
from superhp_agent.storage import AppDB


class VocabItem:
    def __init__(self, word: str, translation: str, context: str = "", pos: str = "other"):
        self.word = word
        self.translation = translation
        self.context = context
        self.pos = pos


def write_unit(root: Path, *, profile_id: str = "english_novel"):
    path = root / "hp01" / "ch01" / "01.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""---
id: hp01-ch01
chapter_id: hp01-ch01
book_id: hp01
book_title: "Harry Potter and the Philosopher's Stone"
chapter_no: 1
chapter_title: "The Boy Who Lived"
summary: "Summary"
profile_id: {profile_id}
---

Body text.
""",
        encoding="utf-8",
    )


def write_classical_unit(root: Path):
    path = root / "classical_chinese" / "lunyu-xueer.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """---
id: cc-lunyu-xueer-01
chapter_id: cc-lunyu-xueer-01
book_id: cc-lunyu
book_title: "论语"
chapter_no: 1
chapter_title: "学而"
summary: "Summary"
profile_id: classical_chinese
---

学而时习之，不亦说乎？
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
    db.add_vocabulary_items(unit, [VocabItem(word="WAND", translation="魔杖", context="second")])

    rows = db.list_vocabulary(unit_id="hp01-ch01")
    assert len(rows) == 1
    assert rows[0]["word"] == "WAND"
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
    assert db.list_mastered_words() == ["crutches"]

    assert db.set_mastered(vocab_id, False)
    assert db.list_vocabulary(unit_id="hp01-ch01")[0]["mastered"] == 0
    assert db.count_vocabulary_for_unit("hp01-ch01") == 1
    assert db.list_mastered_words() == []

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
        context="half-[[exasperated|恼怒的|adjective]], half-[[admiring|钦佩的]].",
    )

    rows = db.list_vocabulary(unit_id="hp01-ch01")
    assert rows[0]["context"] == "half-exasperated, half-admiring."


def test_vocabulary_accepts_classical_chinese_pos_labels(tmp_path):
    corpus_root = tmp_path / "corpus"
    write_unit(corpus_root)
    unit = CorpusStore(corpus_root).get_unit("hp01-ch01").meta
    db = AppDB(tmp_path / "app.sqlite3")

    db.add_vocabulary_items(unit, [VocabItem(word="说", translation="同“悦”，愉快", pos="通假字")])

    rows = db.list_vocabulary(unit_id="hp01-ch01")
    assert rows[0]["pos"] == "通假字"


def test_vocabulary_upgrades_chinese_other_pos_label(tmp_path):
    corpus_root = tmp_path / "corpus"
    write_classical_unit(corpus_root)
    unit = CorpusStore(corpus_root).get_unit("cc-lunyu-xueer-01").meta
    db = AppDB(tmp_path / "app.sqlite3")

    db.add_vocabulary_items(unit, [VocabItem(word="说", translation="愉快", pos="其他")])
    db.add_vocabulary_items(unit, [VocabItem(word="说", translation="同“悦”，愉快", pos="通假字")])

    rows = db.list_vocabulary(unit_id="cc-lunyu-xueer-01")
    assert rows[0]["pos"] == "通假字"


def test_vocabulary_can_be_filtered_by_profile(tmp_path):
    corpus_root = tmp_path / "corpus"
    write_unit(corpus_root)
    write_classical_unit(corpus_root)
    store = CorpusStore(corpus_root)
    english_unit = store.get_unit("hp01-ch01").meta
    classical_unit = store.get_unit("cc-lunyu-xueer-01").meta
    db = AppDB(tmp_path / "app.sqlite3")

    db.add_vocabulary_items(english_unit, [VocabItem(word="wand", translation="魔杖", pos="noun")])
    db.add_vocabulary_items(classical_unit, [VocabItem(word="说", translation="同“悦”，愉快", pos="通假字")])

    english_rows = db.list_vocabulary(profile_id="english_novel")
    classical_rows = db.list_vocabulary(profile_id="classical_chinese")

    assert [row["word"] for row in english_rows] == ["wand"]
    assert [row["word"] for row in classical_rows] == ["说"]


def test_same_word_is_isolated_by_profile(tmp_path):
    corpus_root = tmp_path / "corpus"
    write_unit(corpus_root)
    write_classical_unit(corpus_root)
    store = CorpusStore(corpus_root)
    english_unit = store.get_unit("hp01-ch01").meta
    classical_unit = store.get_unit("cc-lunyu-xueer-01").meta
    db = AppDB(tmp_path / "app.sqlite3")

    english_id = db.add_manual_vocabulary(
        english_unit,
        word="Master",
        translation="主人",
        pos="noun",
    )
    classical_id = db.add_manual_vocabulary(
        classical_unit,
        word="master",
        translation="掌握",
        pos="重点实词",
    )

    assert english_id != classical_id
    assert db.set_mastered_by_word("MASTER", True, profile_id="english_novel")
    english_row = db.list_vocabulary(profile_id="english_novel")[0]
    classical_row = db.list_vocabulary(profile_id="classical_chinese")[0]
    assert english_row["translation"] == "主人"
    assert english_row["mastered"] == 1
    assert classical_row["translation"] == "掌握"
    assert classical_row["mastered"] == 0
    assert db.list_mastered_words("english_novel") == ["Master"]
    assert db.list_mastered_words("classical_chinese") == []


def test_find_mastered_words_returns_only_relevant_profile_candidates(tmp_path):
    corpus_root = tmp_path / "corpus"
    write_unit(corpus_root)
    write_classical_unit(corpus_root)
    store = CorpusStore(corpus_root)
    english_unit = store.get_unit("hp01-ch01").meta
    classical_unit = store.get_unit("cc-lunyu-xueer-01").meta
    db = AppDB(tmp_path / "app.sqlite3")

    wand_id = db.add_manual_vocabulary(english_unit, word="Wand", translation="魔杖")
    cloak_id = db.add_manual_vocabulary(english_unit, word="cloak", translation="斗篷")
    chinese_id = db.add_manual_vocabulary(classical_unit, word="说", translation="愉快")
    db.set_mastered(wand_id, True)
    db.set_mastered(cloak_id, True)
    db.set_mastered(chinese_id, True)

    assert db.find_mastered_words(
        "english_novel",
        {"wand", "table", "说"},
    ) == ["Wand"]
    assert db.find_mastered_words("classical_chinese", {"wand", "说"}) == ["说"]
    assert db.find_mastered_words("english_novel", set()) == []


def test_bookmarks_can_be_listed_filtered_and_deleted(tmp_path):
    corpus_root = tmp_path / "corpus"
    write_unit(corpus_root)
    unit = CorpusStore(corpus_root).get_unit("hp01-ch01").meta
    db = AppDB(tmp_path / "app.sqlite3")

    first_id = db.add_bookmark(
        unit,
        body_kind="source",
        page_index=2,
        progress_ratio=0.25,
        total_pages=8,
        label="Chapter 1 · Page 3",
        excerpt="Mr and Mrs Dursley...",
        annotation_level="advanced",
        paragraph_index=4,
    )
    second_id = db.add_bookmark(
        unit,
        body_kind="annotated",
        page_index=4,
        progress_ratio=0.5,
        total_pages=8,
        label="Annotated page",
        annotation_level="advanced",
        paragraph_index=9,
    )

    rows = db.list_bookmarks(unit_id="hp01-ch01")
    assert [row["id"] for row in rows] == [second_id, first_id]
    assert rows[0]["body_kind"] == "annotated"
    assert rows[0]["annotation_level"] == "advanced"
    assert rows[0]["paragraph_index"] == 9
    assert rows[1]["excerpt"] == "Mr and Mrs Dursley..."
    assert rows[1]["annotation_level"] == ""
    assert rows[1]["paragraph_index"] == 4

    assert db.delete_bookmark(first_id)
    assert [row["id"] for row in db.list_bookmarks()] == [second_id]
    assert not db.delete_bookmark(first_id)


def test_bookmark_rejects_unknown_body_kind(tmp_path):
    corpus_root = tmp_path / "corpus"
    write_unit(corpus_root)
    unit = CorpusStore(corpus_root).get_unit("hp01-ch01").meta
    db = AppDB(tmp_path / "app.sqlite3")

    try:
        db.add_bookmark(unit, body_kind="notes", page_index=0)
    except ValueError as exc:
        assert "body_kind" in str(exc)
    else:
        raise AssertionError("expected invalid bookmark body_kind to fail")
