"""Sliding three-chapter evaluation tests for shadow-mode adaptation."""

from superhp_agent.application import (
    ReadingAdaptationAction,
    ReadingAdaptationEvaluator,
)
from superhp_agent.contracts import ChapterReadingCheckpoint
from superhp_agent.storage import AppDB


class RecordingEventLogger:
    def __init__(self):
        self.events = []

    def log_event(self, event_type, **payload):
        self.events.append({"type": event_type, **payload})


def _checkpoint(
    chapter_no: int,
    *,
    book_id: str = "book-1",
    lookup_count: int = 0,
    annotated_lookup_count: int = 0,
    annotation_target: int | None = 8,
) -> ChapterReadingCheckpoint:
    chapter_id = f"{book_id}-ch{chapter_no:02d}"
    return ChapterReadingCheckpoint(
        book_id=book_id,
        chapter_id=chapter_id,
        chapter_no=chapter_no,
        unit_ids=(chapter_id,),
        word_count=100,
        lookup_count=lookup_count,
        annotated_lookup_count=annotated_lookup_count,
        annotation_target=annotation_target,
    )


def test_evaluator_starts_at_three_chapters_then_slides_one_chapter(tmp_path):
    db = AppDB(tmp_path / "app.db")
    evaluator = ReadingAdaptationEvaluator(
        db.chapter_checkpoint_repository,
        db.reading_support_repository,
    )

    try:
        for chapter_no in (1, 2):
            db.chapter_checkpoint_repository.record(
                _checkpoint(chapter_no, lookup_count=4)
            )
            assert evaluator.evaluate_book("book-1") is None

        db.chapter_checkpoint_repository.record(
            _checkpoint(3, lookup_count=4)
        )
        first = evaluator.evaluate_book("book-1")

        assert first is not None
        assert first.window.chapter_ids == (
            "book-1-ch01",
            "book-1-ch02",
            "book-1-ch03",
        )
        assert first.window.evidence.observed_chapter_count == 3
        assert first.window.evidence.observed_word_count == 300
        assert first.window.evidence.lookup_density == 12
        assert first.decision is not None
        assert first.decision.action is ReadingAdaptationAction.INCREASE
        assert first.decision.next_target == 10
        assert db.get_annotation_target("book-1") == 8
        assert (
            db.get_state("book-1").last_evaluated_chapter_id
            == "book-1-ch03"
        )
        assert evaluator.evaluate_book("book-1") is None

        db.chapter_checkpoint_repository.record(_checkpoint(4))
        second = evaluator.evaluate_book("book-1")

        assert second is not None
        assert second.window.chapter_ids == (
            "book-1-ch02",
            "book-1-ch03",
            "book-1-ch04",
        )
        assert second.window.evidence.lookup_density == 8
        assert second.decision is not None
        assert second.decision.action is ReadingAdaptationAction.HOLD
        assert db.get_annotation_target("book-1") == 8
    finally:
        db.close()


def test_evaluator_keeps_new_book_at_default_independent_state(tmp_path):
    db = AppDB(tmp_path / "app.db")
    evaluator = ReadingAdaptationEvaluator(
        db.chapter_checkpoint_repository,
        db.reading_support_repository,
    )

    try:
        db.set_annotation_target("book-1", 14)
        for chapter_no in (1, 2, 3):
            db.chapter_checkpoint_repository.record(
                _checkpoint(
                    chapter_no,
                    book_id="book-2",
                    lookup_count=1,
                )
            )

        evaluation = evaluator.evaluate_book("book-2")

        assert evaluation is not None
        assert evaluation.window.evidence.annotation_target == 8
        assert db.get_annotation_target("book-1") == 14
        assert db.get_annotation_target("book-2") == 8
    finally:
        db.close()


def test_evaluator_waits_for_three_matching_chapters_after_target_change(
    tmp_path,
):
    db = AppDB(tmp_path / "app.db")
    evaluator = ReadingAdaptationEvaluator(
        db.chapter_checkpoint_repository,
        db.reading_support_repository,
    )

    try:
        db.set_annotation_target("book-1", 10)
        for chapter_no in (1, 2):
            db.chapter_checkpoint_repository.record(
                _checkpoint(chapter_no, annotation_target=10)
            )
            assert evaluator.evaluate_book("book-1") is None

        assert db.get_state("book-1").cooldown_chapters_remaining == 1

        db.chapter_checkpoint_repository.record(
            _checkpoint(3, annotation_target=10)
        )
        evaluation = evaluator.evaluate_book("book-1")

        assert evaluation is not None
        assert evaluation.cooldown_chapters_remaining == 0
        assert evaluation.decision is not None
        assert evaluation.decision.action is ReadingAdaptationAction.HOLD
        assert db.get_state("book-1").cooldown_chapters_remaining == 0
        assert db.get_annotation_target("book-1") == 10
    finally:
        db.close()


def test_evaluator_logs_shadow_decision_without_applying_it(tmp_path):
    db = AppDB(tmp_path / "app.db")
    evaluator = ReadingAdaptationEvaluator(
        db.chapter_checkpoint_repository,
        db.reading_support_repository,
    )
    logger = RecordingEventLogger()

    try:
        for chapter_no in (1, 2, 3):
            db.chapter_checkpoint_repository.record(
                _checkpoint(chapter_no, lookup_count=4)
            )

        evaluator.evaluate_and_log("book-1", logger)

        assert logger.events[0]["type"] == "reading_adaptation_evaluated"
        assert logger.events[0]["chapter_ids"] == [
            "book-1-ch01",
            "book-1-ch02",
            "book-1-ch03",
        ]
        assert logger.events[0]["action"] == "increase"
        assert logger.events[0]["current_target"] == 8
        assert logger.events[0]["proposed_target"] == 10
        assert logger.events[0]["shadow_mode"] is True
        assert db.get_annotation_target("book-1") == 8
    finally:
        db.close()
