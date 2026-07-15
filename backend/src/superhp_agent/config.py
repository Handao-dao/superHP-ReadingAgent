"""Application configuration and derived filesystem locations.

The backend keeps immutable reading source files in ``corpus/`` and mutable
runtime artifacts in ``data/``. Centralizing those paths here makes the rest of
the code depend on named capabilities instead of hard-coded directories.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    """Environment-driven settings shared by HTTP, WebSocket, and services."""

    # Mutable state lives under data_dir so it can be ignored by git and reset
    # without touching the source corpus.
    data_dir: Path = Field(default=BACKEND_ROOT / "data")
    corpus_dir: Path = Field(default=PROJECT_ROOT / "corpus")
    llm_provider: str = "deepseek"
    llm_model_id: str = "deepseek-v4-pro"
    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: str = ""
    llm_timeout: int = 60
    llm_temperature: float = 0.2
    llm_max_tokens: int = 8192
    annotation_max_chunk_words: int = 1000
    annotation_max_concurrency: int = Field(default=8, ge=1, le=32)
    default_profile_id: str = "english_novel"

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
    )

    @model_validator(mode="after")
    def resolve_relative_paths(self) -> "Settings":
        """Keep env-file paths stable regardless of the process cwd."""
        if not self.data_dir.is_absolute():
            self.data_dir = BACKEND_ROOT / self.data_dir
        if not self.corpus_dir.is_absolute():
            self.corpus_dir = BACKEND_ROOT / self.corpus_dir
        return self

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
    def event_log_path(self) -> Path:
        return self.memory_dir / "events.jsonl"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings object so services share one configuration."""
    return Settings()
