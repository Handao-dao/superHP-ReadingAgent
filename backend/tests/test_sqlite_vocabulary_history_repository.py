"""SQLite integration tests for scoped vocabulary-history retrieval."""

from pathlib import Path

from superhp_agent.corpus import ReadingUnit
from superhp_agent.ports import VocabularyHistoryRepository
from superhp_agent.storage import AppDB
from superhp_agent.storage.sqlite import (
    SQLiteVocabularyHistoryRepository,
)


class VocabItem:
    def __init__(self, word: str, translation: str, context: str):
        self.word = word
        self.translation = translation
        self.context = context
        self.pos = "verb"


def _unit(
    *,
    unit_id: str,
    chapter_no: int,
    book_id: str = "book-1",
) -> ReadingUnit:
    return ReadingUnit(
        id=unit_id,
        chapter_id=f"{book_id}-ch{chapter_no:02d}",
        book_id=book_id,
        book_title=f"Book {book_id}",
        chapter_no=chapter_no,
        chapter_title=f"Chapter {chapter_no}",
        section_no=1,
        section_count=1,
        summary="",
        path=Path(f"{unit_id}.md"),
    )


def test_sqlite_history_is_exact_book_local_and_scope_limited(tmp_path):
    db = AppDB(tmp_path / "app.sqlite3")
    units = (
        _unit(unit_id="book-1-ch1", chapter_no=1),
        _unit(unit_id="book-1-ch2", chapter_no=2),
        _unit(unit_id="book-1-ch3-unread", chapter_no=3),
        _unit(unit_id="book-2-ch1", chapter_no=1, book_id="book-2"),
    )
    try:
        for unit, translation, context in (
            (units[0], "收费", "The hotel charged ten pounds."),
            (units[1], "指控", "He was charged with theft."),
            (units[2], "冲锋", "They charge at dawn."),
            (units[3], "负责", "She is in charge of the case."),
        ):
            db.add_vocabulary_items(
                unit,
                [VocabItem("charge", translation, context)],
            )
        db.add_vocabulary_items(
            units[1],
            [VocabItem("charged", "被指控", "He looked shocked.")],
        )
        db.set_mastered_by_word("charge", True, language_id="en")

        repository = db.vocabulary_history_repository
        encounters = repository.find_encounters(
            language_id="en",
            normalized_word="charge",
            book_id="book-1",
            allowed_unit_ids=(
                "book-1-ch1",
                "book-1-ch2",
                "book-2-ch1",
            ),
            limit=5,
        )

        assert isinstance(repository, SQLiteVocabularyHistoryRepository)
        assert isinstance(repository, VocabularyHistoryRepository)
        assert [item.chapter_no for item in encounters] == [1, 2]
        assert [item.translation for item in encounters] == ["收费", "指控"]
        assert all(item.book_id == "book-1" for item in encounters)
        assert all(item.normalized_word == "charge" for item in encounters)
        assert all(item.mastered is True for item in encounters)
    finally:
        db.close()


def test_sqlite_history_returns_latest_limit_in_chronological_order(tmp_path):
    db = AppDB(tmp_path / "app.sqlite3")
    units = tuple(
        _unit(unit_id=f"book-1-ch{chapter_no}", chapter_no=chapter_no)
        for chapter_no in range(1, 5)
    )
    try:
        for unit in units[:3]:
            db.add_vocabulary_items(
                unit,
                [
                    VocabItem(
                        "clue",
                        "线索",
                        f"Context from chapter {unit.chapter_no}.",
                    )
                ],
            )
        db.add_vocabulary_items(
            units[3],
            [VocabItem("clue", "线索", "")],
        )

        encounters = db.vocabulary_history_repository.find_encounters(
            language_id="en",
            normalized_word="clue",
            book_id="book-1",
            allowed_unit_ids=tuple(unit.id for unit in units),
            limit=2,
        )

        assert [item.chapter_no for item in encounters] == [2, 3]
        assert (
            db.vocabulary_history_repository.find_encounters(
                language_id="en",
                normalized_word="clue",
                book_id="book-1",
                allowed_unit_ids=(),
                limit=2,
            )
            == ()
        )
    finally:
        db.close()
