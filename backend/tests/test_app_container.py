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
        assert container.bookmark_repository is container.db.bookmark_repository
        assert (
            container.reading_progress_repository
            is container.db.reading_progress_repository
        )
        assert container.book_difficulty_catalog is container.db.book_difficulty_catalog
        assert (
            container.recommendation_candidate_service.catalog
            is container.book_difficulty_catalog
        )
        assert (
            container.book_catalog_search_tool.service
            is container.recommendation_candidate_service
        )
        assert container.recommendation_tool_registry.describe(
            ("search_local_book_catalog",)
        )[0]["name"] == "search_local_book_catalog"
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
