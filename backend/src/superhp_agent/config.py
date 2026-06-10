"""Application configuration and derived filesystem locations.

The backend keeps immutable reading source files in ``corpus/`` and mutable
runtime artifacts in ``data/``. Centralizing those paths here makes the rest of
the code depend on named capabilities instead of hard-coded directories.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven settings shared by HTTP, WebSocket, and services."""

    # Mutable state lives under data_dir so it can be ignored by git and reset
    # without touching the source corpus.
    data_dir: Path = Field(default=Path("./data"))
    corpus_dir: Path = Field(default=Path("../corpus"))
    llm_provider: str = "deepseek"
    llm_model_id: str = "deepseek-v4-pro"
    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: str = ""
    llm_timeout: int = 60
    llm_temperature: float = 0.2
    llm_max_tokens: int = 8192
    annotation_max_chunk_words: int = 1000
    annotation_max_concurrency: int = 100

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def db_path(self) -> Path:
        """SQLite database for queryable vocabulary and progress tables."""
        return self.data_dir / "superhp.sqlite3"

    @property
    def annotated_dir(self) -> Path:
        """Generated annotated Markdown copies, keyed by reading-unit id."""
        return self.data_dir / "annotated_corpus"

    @property
    def memory_dir(self) -> Path:
        """Small file-backed memory records for the guided reading flow."""
        return self.data_dir / "memory"

    @property
    def reading_memory_path(self) -> Path:
        return self.memory_dir / "reading_memory.json"

    @property
    def event_log_path(self) -> Path:
        return self.memory_dir / "events.jsonl"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings object so services share one configuration."""
    return Settings()
