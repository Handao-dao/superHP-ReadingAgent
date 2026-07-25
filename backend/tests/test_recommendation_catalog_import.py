"""Tests for the explicit recommendation-catalog import tool."""

import importlib.util
import sys
from pathlib import Path

from superhp_agent.contracts import BookEntryKind

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "import_recommendation_catalog.py"
)
SPEC = importlib.util.spec_from_file_location("catalog_import", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
catalog_import = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = catalog_import
SPEC.loader.exec_module(catalog_import)


def test_parse_source_line_handles_range_and_cleans_notes():
    book = catalog_import.parse_source_line(
        "880-940L HP 哈利波特",
        source_index=1,
    )

    assert book.search_title == "Harry Potter"
    assert book.title_zh == "哈利波特"
    assert book.difficulty_min == 880
    assert book.difficulty_max == 940
    assert book.entry_kind is BookEntryKind.SERIES


def test_parse_source_line_handles_missing_space_after_l():
    book = catalog_import.parse_source_line(
        "590LA night on smugglers' Island",
        source_index=1,
    )

    assert book.title_en == "A night on smugglers' Island"
    assert book.difficulty_min == 590


def test_title_similarity_tolerates_series_volume_suffix():
    score = catalog_import.title_similarity(
        "Magic Tree House",
        "Magic Tree House: Dinosaurs Before Dark",
    )

    assert score >= 0.8


def test_tags_for_uses_stable_override_and_public_metadata():
    book = catalog_import.parse_source_line(
        "740L A Wrinkle in Time 时间的皱纹",
        source_index=1,
    )
    metadata = catalog_import.MetadataMatch(
        source="google_books",
        title="A Wrinkle in Time",
        authors=("Madeleine L'Engle",),
        subjects=("Juvenile Fiction / Science Fiction",),
        description="A time travel adventure about family.",
        confidence=1.0,
    )

    assert catalog_import.tags_for(book, metadata) == (
        "fantasy",
        "science_fiction",
        "adventure",
    )


def test_tags_for_does_not_trust_weak_metadata():
    book = catalog_import.parse_source_line(
        "500L The Wizard of Oz 绿野仙踪",
        source_index=1,
    )
    metadata = catalog_import.MetadataMatch(
        source="google_books",
        title="Unrelated Book",
        authors=(),
        subjects=("True crime",),
        description="",
        confidence=0.2,
    )

    assert "crime" not in catalog_import.tags_for(book, metadata)
    assert "fantasy" in catalog_import.tags_for(book, metadata)


def test_corrected_ambiguous_title_uses_manual_style_tags():
    book = catalog_import.parse_source_line(
        "830L Worth 纽伯瑞奖",
        source_index=1,
    )

    assert book.search_title == "Worth (A. LaFaye)"
    assert catalog_import.tags_for(book, None) == (
        "historical_fiction",
        "realistic_fiction",
        "family_friendship",
    )


def test_enrich_books_offline_keeps_source_difficulty_and_tags():
    book = catalog_import.parse_source_line(
        "240-500L Magic Tree House 神奇树屋",
        source_index=1,
    )

    candidates, records = catalog_import.enrich_books(
        [book],
        offline=True,
        user_agent="test",
        delay_seconds=0,
        workers=1,
        google_enabled=False,
        allow_open_library=False,
    )

    assert candidates[0].difficulty.minimum_lexile == 240
    assert candidates[0].genres == (
        "adventure",
        "fantasy",
        "historical_fiction",
    )
    assert records[0].matched_source == ""
