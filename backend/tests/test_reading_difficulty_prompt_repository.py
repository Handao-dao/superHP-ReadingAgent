"""Persistence and coordination tests for chapter-end difficulty prompts."""

from superhp_agent.application import ReadingDifficultyPromptCoordinator
from superhp_agent.contracts import ReadingDifficultyEvidence
from superhp_agent.domain.reading_difficulty_prompt import (
    ReadingDifficultyPromptStatus,
)
from superhp_agent.domain.reading_support import ReadingSupportState
from superhp_agent.ports import ReadingDifficultyPromptRepository
from superhp_agent.storage import AppDB
from superhp_agent.storage.sqlite import (
    SQLiteReadingDifficultyPromptRepository,
)


def _evidence() -> ReadingDifficultyEvidence:
    return ReadingDifficultyEvidence(
        observed_word_count=7200,
        observed_chapter_count=3,
        lookup_density=12.1,
        annotated_lookup_density=3.2,
        annotation_target=20,
    )


def test_prompt_repository_persists_choice_and_unique_chapter_cooldown(
    tmp_path,
):
    db = AppDB(tmp_path / "app.db")
    repository = db.reading_difficulty_prompt_repository
    try:
        assert isinstance(repository, ReadingDifficultyPromptRepository)
        assert isinstance(
            repository,
            SQLiteReadingDifficultyPromptRepository,
        )

        pending = repository.open_prompt(
            book_id="book-1",
            chapter_id="book-1-ch03",
            evidence=_evidence(),
        )
        assert pending.status is ReadingDifficultyPromptStatus.PENDING
        assert repository.get("book-1") == pending

        continued = repository.choose_continue(
            "book-1",
            cooldown_chapters=3,
        )
        assert (
            continued.status
            is ReadingDifficultyPromptStatus.CONTINUE_READING
        )
        assert continued.cooldown_chapters_remaining == 3

        same_chapter = repository.advance_cooldown(
            "book-1",
            chapter_id="book-1-ch03",
        )
        first_new_chapter = repository.advance_cooldown(
            "book-1",
            chapter_id="book-1-ch04",
        )
        duplicate = repository.advance_cooldown(
            "book-1",
            chapter_id="book-1-ch04",
        )
        assert same_chapter.cooldown_chapters_remaining == 3
        assert first_new_chapter.cooldown_chapters_remaining == 2
        assert duplicate.cooldown_chapters_remaining == 2
    finally:
        db.close()


def test_prompt_coordinator_resets_confirmation_and_links_agent_session(
    tmp_path,
):
    db = AppDB(tmp_path / "app.db")
    coordinator = ReadingDifficultyPromptCoordinator(
        db.reading_difficulty_prompt_repository,
        db.reading_support_repository,
    )
    try:
        db.save_evaluation_state(
            "book-1",
            ReadingSupportState(
                annotation_target=20,
                max_target_high_density_streak=2,
            ),
        )
        db.reading_difficulty_prompt_repository.open_prompt(
            book_id="book-1",
            chapter_id="book-1-ch03",
            evidence=_evidence(),
        )

        continued = coordinator.choose_continue("book-1")

        assert continued.cooldown_chapters_remaining == 3
        assert db.get_state("book-1").max_target_high_density_streak == 0
        assert (
            db.get_state("book-1").last_decision
            == "difficulty_prompt:continue_reading"
        )

        db.reading_difficulty_prompt_repository.open_prompt(
            book_id="book-1",
            chapter_id="book-1-ch07",
            evidence=_evidence(),
        )
        changed = coordinator.choose_change_book(
            "book-1",
            recommendation_session_id="recommendation-1",
        )

        assert changed.status is ReadingDifficultyPromptStatus.CHANGE_BOOK
        assert changed.recommendation_session_id == "recommendation-1"
        assert (
            db.get_state("book-1").last_decision
            == "difficulty_prompt:change_book"
        )
    finally:
        db.close()
