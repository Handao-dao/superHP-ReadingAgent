"""Domain and compatibility tests for vocabulary classification rules."""

import pytest

from superhp_agent.domain import (
    extract_vocabulary_candidates,
    normalize_pos,
    normalize_word,
)
from superhp_agent.storage import normalize_pos as legacy_normalize_pos


def test_normalize_word_builds_case_insensitive_identity():
    assert normalize_word("  Straße  ") == "strasse"
    assert normalize_word(" 学而 ") == "学而"


def test_extract_vocabulary_candidates_supports_short_phrases_and_cjk():
    candidates = extract_vocabulary_candidates("Give up, now. 学而时习之。")

    assert {"give", "give up", "up", "now"} <= candidates
    assert "up now" not in candidates
    assert {"学", "学而", "而时习之"} <= candidates
    assert "学而时习之" not in candidates


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("n", "noun"),
        ("V", "verb"),
        (" adj ", "adjective"),
        ("ADV", "adverb"),
        ("phrase", "phrase"),
        ("通假字", "通假字"),
        ("其他", "其他"),
        ("unknown", "other"),
        (None, "other"),
    ],
)
def test_normalize_pos(raw, expected):
    assert normalize_pos(raw) == expected


def test_storage_keeps_legacy_normalize_pos_import():
    assert legacy_normalize_pos is normalize_pos
