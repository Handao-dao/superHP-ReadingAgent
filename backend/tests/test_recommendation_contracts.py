"""Tests for book-recommendation contracts and their invariants."""

from dataclasses import FrozenInstanceError

import pytest

from superhp_agent.contracts import (
    BookCandidate,
    BookDifficulty,
    BookRecommendationHandoff,
    BookSearchQuery,
    BookSnapshot,
    OperationalReadingBand,
    ReadingDifficultyEvidence,
    ReadingPreference,
    RecommendationOrigin,
    RecommendationOutcome,
    RecommendationOutcomeKind,
    RecommendationRequest,
)


def test_difficulty_alert_request_carries_structured_reading_evidence():
    current_book = BookSnapshot(
        book_id="book-1",
        title="A Mystery",
        isbn="9780000000001",
        lexile_measure=900,
        genres=("mystery",),
        progress=0.25,
    )
    evidence = ReadingDifficultyEvidence(
        observed_word_count=7200,
        observed_chapter_count=3,
        lookup_density=12.1,
        unique_lookup_density=9.8,
        repeated_lookup_density=2.3,
        actual_annotation_density=16.0,
        annotation_target=16,
    )
    target_band = OperationalReadingBand(
        minimum_lexile=700,
        maximum_lexile=850,
        confidence=0.7,
        evidence_source="reading_monitor",
    )
    handoff = BookRecommendationHandoff(
        current_book=current_book,
        evidence=evidence,
        target_band=target_band,
    )

    request = RecommendationRequest(
        origin=RecommendationOrigin.DIFFICULTY_ALERT,
        preferred_genres=("mystery",),
        reading_preference=ReadingPreference.FLUENCY_FIRST,
        handoff=handoff,
    )

    assert request.handoff is not None
    assert request.handoff.evidence.lookup_density == 12.1
    assert request.handoff.target_band == target_band
    assert request.preferred_genres == ("mystery",)


def test_catalog_candidate_keeps_measure_source_and_edition_identity():
    difficulty = BookDifficulty(
        isbn="9780000000002",
        lexile_measure=760,
        source="manual_test_catalog",
        is_certified=True,
    )
    candidate = BookCandidate(
        catalog_id="candidate-1",
        title="An Easier Mystery",
        author="A. Writer",
        isbn=difficulty.isbn,
        difficulty=difficulty,
        genres=("mystery",),
        available_locally=True,
    )

    assert candidate.difficulty == difficulty
    assert candidate.difficulty.is_certified is True
    assert candidate.available_locally is True


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (
            lambda: OperationalReadingBand(900, 700),
            "minimum_lexile",
        ),
        (
            lambda: OperationalReadingBand(700, 900, confidence=1.1),
            "confidence",
        ),
        (
            lambda: BookSnapshot(book_id="book", title="Book", progress=1.1),
            "progress",
        ),
        (
            lambda: ReadingDifficultyEvidence(
                observed_word_count=-1,
                observed_chapter_count=0,
                lookup_density=0,
            ),
            "must not be negative",
        ),
        (
            lambda: BookSearchQuery(lexile_min=900, lexile_max=700),
            "lexile_min",
        ),
        (
            lambda: BookSearchQuery(limit=0),
            "limit",
        ),
    ],
)
def test_recommendation_contracts_reject_invalid_boundary_values(factory, message):
    with pytest.raises(ValueError, match=message):
        factory()


def test_recommendation_contracts_are_immutable():
    request = RecommendationRequest(origin=RecommendationOrigin.ONBOARDING)

    with pytest.raises(FrozenInstanceError):
        request.user_notes = "changed"


def test_recommendation_outcome_defaults_to_unknown_until_enough_evidence():
    outcome = RecommendationOutcome(
        recommendation_id="rec-1",
        selected_book=BookSnapshot(book_id="book-1", title="Book"),
    )

    assert outcome.kind is RecommendationOutcomeKind.UNKNOWN
    assert outcome.observed_word_count == 0
    assert outcome.notes == ()
