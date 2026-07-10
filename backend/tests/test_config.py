import pytest
from pydantic import ValidationError

from superhp_agent.config import BACKEND_ROOT, PROJECT_ROOT, Settings


def test_settings_defaults_are_independent_of_cwd(monkeypatch, tmp_path):
    monkeypatch.delenv("DATA_DIR", raising=False)
    monkeypatch.delenv("CORPUS_DIR", raising=False)
    monkeypatch.chdir(tmp_path)

    settings = Settings(_env_file=None)

    assert settings.data_dir == BACKEND_ROOT / "data"
    assert settings.corpus_dir == PROJECT_ROOT / "corpus"
    assert settings.annotation_max_chunk_words == 1500
    assert settings.annotation_max_concurrency == 8


def test_settings_resolves_relative_env_paths_from_backend_root(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", "./custom-data")
    monkeypatch.setenv("CORPUS_DIR", "../custom-corpus")
    monkeypatch.chdir(tmp_path)

    settings = Settings(_env_file=None)

    assert settings.data_dir == BACKEND_ROOT / "custom-data"
    assert settings.corpus_dir == BACKEND_ROOT / "../custom-corpus"


def test_settings_keeps_absolute_paths(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    corpus_dir = tmp_path / "corpus"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("CORPUS_DIR", str(corpus_dir))

    settings = Settings(_env_file=None)

    assert settings.data_dir == data_dir
    assert settings.corpus_dir == corpus_dir


@pytest.mark.parametrize("value", ["0", "33"])
def test_settings_rejects_unsafe_annotation_concurrency(monkeypatch, value):
    monkeypatch.setenv("ANNOTATION_MAX_CONCURRENCY", value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
