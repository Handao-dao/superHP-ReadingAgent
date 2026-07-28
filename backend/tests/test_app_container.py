"""Composition tests for the backend application container."""

import pytest

from superhp_agent.application import AppContainer, build_container
from superhp_agent.config import Settings
from superhp_agent.library_catalog import LibraryCatalogError
from superhp_agent.profiles import UnknownProfileError


def test_build_container_wires_shared_capabilities(tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data",
        corpus_dir=tmp_path / "corpus",
        llm_api_key="",
    )

    container = build_container(settings)

    try:
        assert isinstance(container, AppContainer)
        assert container.settings is settings
        assert container.event_log_store.event_log_path == settings.event_log_path
        assert not (settings.memory_dir / "reading_memory.json").exists()
        assert container.vocabulary_repository is container.db.vocabulary_repository
        assert (
            container.vocabulary_history_repository
            is container.db.vocabulary_history_repository
        )
        assert container.bookmark_repository is container.db.bookmark_repository
        assert (
            container.reading_progress_repository
            is container.db.reading_progress_repository
        )
        assert (
            container.reading_support_repository
            is container.db.reading_support_repository
        )
        assert (
            container.reading_difficulty_prompt_repository
            is container.db.reading_difficulty_prompt_repository
        )
        assert (
            container.chapter_checkpoint_repository
            is container.db.chapter_checkpoint_repository
        )
        assert (
            container.chapter_checkpoint_recorder.checkpoint_repository
            is container.chapter_checkpoint_repository
        )
        assert (
            container.reading_adaptation_evaluator.checkpoint_repository
            is container.chapter_checkpoint_repository
        )
        assert (
            container.reading_adaptation_evaluator.support_repository
            is container.reading_support_repository
        )
        assert (
            container.reading_adaptation_evaluator.prompt_repository
            is container.reading_difficulty_prompt_repository
        )
        assert (
            container.reading_difficulty_prompt_coordinator.prompt_repository
            is container.reading_difficulty_prompt_repository
        )
        assert (
            container.recommendation_session_repository
            is container.db.recommendation_session_repository
        )
        assert (
            container.recommendation_agent_runner.session_repository
            is container.recommendation_session_repository
        )
        assert container.book_difficulty_catalog is container.db.book_difficulty_catalog
        assert container.difficulty_handoff_builder.corpus is container.corpus
        assert (
            container.difficulty_handoff_builder.library_catalog
            is container.library_catalog
        )
        assert (
            container.difficulty_handoff_builder.difficulty_catalog
            is container.book_difficulty_catalog
        )
        assert (
            container.difficulty_handoff_builder.progress_repository
            is container.reading_progress_repository
        )
        assert (
            container.recommendation_candidate_service.catalog
            is container.book_difficulty_catalog
        )
        assert (
            container.book_catalog_search_tool.service
            is container.recommendation_candidate_service
        )
        assert (
            container.recommendation_tool_registry
            is container.agent_tool_registry
        )
        assert (
            container.previous_reading_scope_builder.checkpoint_repository
            is container.chapter_checkpoint_repository
        )
        assert (
            container.previous_chapter_search_tool.service
            is container.previous_chapter_search_service
        )
        assert (
            container.vocabulary_history_search_service.repository
            is container.vocabulary_history_repository
        )
        assert (
            container.vocabulary_history_search_tool.service
            is container.vocabulary_history_search_service
        )
        assert (
            container.manual_reading_companion_runner.scope_builder
            is container.previous_reading_scope_builder
        )
        assert (
            container.reading_companion_session_coordinator.runner
            is container.manual_reading_companion_runner
        )
        assert (
            container.manual_reading_companion_runner.corpus
            is container.corpus
        )
        assert container.recommendation_tool_registry.describe(
            (
                "search_local_book_catalog",
                "present_book_recommendations",
                "select_recommended_book",
            )
        )[1]["name"] == "present_book_recommendations"
        assert (
            container.recommendation_tool_registry.describe(
                ("select_recommended_book",)
            )[0]["name"]
            == "select_recommended_book"
        )
        assert [
            description["name"]
            for description in container.recommendation_tool_registry.describe(
                (
                    "search_previous_chapters",
                    "search_vocabulary_history",
                )
            )
        ] == [
            "search_previous_chapters",
            "search_vocabulary_history",
        ]
        assert (
            container.state_reader.progress_repository
            is container.reading_progress_repository
        )
        assert container.state_reader.db is container.vocabulary_repository
        assert container.flow_router.state_reader is container.state_reader
    finally:
        container.close()


def test_build_container_rejects_unknown_default_profile(tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data",
        corpus_dir=tmp_path / "corpus",
        default_profile_id="missing",
    )

    with pytest.raises(UnknownProfileError, match="Unknown profile id: missing"):
        build_container(settings)


def test_build_container_rejects_unknown_corpus_profile(tmp_path):
    corpus_dir = tmp_path / "corpus"
    unit_path = corpus_dir / "book" / "chapter.md"
    unit_path.parent.mkdir(parents=True)
    unit_path.write_text(
        """---
id: unknown-profile-unit
book_id: book
book_title: Book
chapter_no: 1
chapter_title: Chapter
profile_id: missing
---

Body.
""",
        encoding="utf-8",
    )
    settings = Settings(data_dir=tmp_path / "data", corpus_dir=corpus_dir)

    with pytest.raises(ValueError, match="Unknown profile in reading unit"):
        build_container(settings)


def test_build_container_rejects_invalid_catalog_policy(tmp_path):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    (corpus_dir / "catalog.yaml").write_text(
        """
collections:
  - id: invalid
    profile_id: english_novel
    selection_policy_id: missing
    title: Invalid
    books: []
""".strip(),
        encoding="utf-8",
    )
    settings = Settings(data_dir=tmp_path / "data", corpus_dir=corpus_dir)

    with pytest.raises(LibraryCatalogError, match="Invalid selection policy"):
        build_container(settings)
