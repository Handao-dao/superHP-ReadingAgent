"""Application configuration."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    data_dir: Path = Field(default=Path("./data"))
    corpus_dir: Path = Field(default=Path("../corpus"))
    llm_provider: str = "deepseek"
    llm_model_id: str = "deepseek-v4-pro"
    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: str = ""
    llm_timeout: int = 60
    llm_temperature: float = 0.2
    llm_max_tokens: int = 4096

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def db_path(self) -> Path:
        return self.data_dir / "superhp.sqlite3"

    @property
    def annotated_dir(self) -> Path:
        return self.data_dir / "annotated_corpus"

    @property
    def memory_dir(self) -> Path:
        return self.data_dir / "memory"

    @property
    def reading_memory_path(self) -> Path:
        return self.memory_dir / "reading_memory.json"

    @property
    def event_log_path(self) -> Path:
        return self.memory_dir / "events.jsonl"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()