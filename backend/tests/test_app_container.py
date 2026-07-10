"""Composition tests for the backend application container."""

from superhp_agent.application import AppContainer, build_container
from superhp_agent.config import Settings


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
        assert (
            container.state_reader.progress_repository
            is container.reading_progress_repository
        )
        assert container.state_reader.db is container.vocabulary_repository
        assert container.flow_router.state_reader is container.state_reader
    finally:
        container.close()
