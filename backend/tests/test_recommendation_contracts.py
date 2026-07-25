"""Tests for book-recommendation contracts and their invariants."""

from dataclasses import FrozenInstanceError

import pytest

from superhp_agent.contracts import (
    BookCandidate,
    BookCandidateMatch,
    BookCandidateMatchResult,
    BookDifficulty,
    BookEntryKind,
    BookRecommendationHandoff,
    BookSearchQuery,
    BookSnapshot,
    OperationalReadingBand,
    ReadingDifficultyEvidence,
    ReadingPreference,
    RecommendationAgentDecision,
    RecommendationAgentDecisionKind,
    RecommendationAgentMessage,
    RecommendationAgentMessageRole,
    RecommendationAgentObservation,
    RecommendationAgentPhase,
    RecommendationAgentReply,
    RecommendationAgentSession,
    RecommendationOrigin,
    RecommendationOutcome,
    RecommendationOutcomeKind,
    RecommendationRequest,
)


def test_difficulty_alert_request_carries_structured_reading_evidence():
    current_book = BookSnapshot(
        book_id="book-1",
        title="A Mystery",
        difficulty=BookDifficulty(900, 900),
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


def test_catalog_candidate_supports_exact_values_and_series_ranges():
    exact_difficulty = BookDifficulty(760, 760)
    candidate = BookCandidate(
        catalog_id="candidate-1",
        title_en="An Easier Mystery",
        title_zh="更简单的谜案",
        author="A. Writer",
        difficulty=exact_difficulty,
        entry_kind=BookEntryKind.BOOK,
        genres=("mystery",),
    )
    series = BookCandidate(
        catalog_id="series-1",
        title_en="Mystery Series",
        difficulty=BookDifficulty(500, 700),
        entry_kind=BookEntryKind.SERIES,
    )

    assert candidate.difficulty.exact_measure == 760
    assert candidate.title_zh == "更简单的谜案"
    assert series.difficulty.exact_measure is None


def test_candidate_match_result_exposes_strict_match_evidence():
    query = BookSearchQuery(categories=("mystery",))
    candidate = BookCandidate(
        catalog_id="candidate",
        title_en="Candidate",
        difficulty=BookDifficulty(700, 700),
        genres=("mystery",),
    )
    result = BookCandidateMatchResult(
        query=query,
        matches=(
            BookCandidateMatch(
                candidate=candidate,
                matched_genres=("mystery",),
                difficulty_distance=25,
            ),
        ),
    )

    assert result.found is True
    assert result.matches[0].difficulty_distance == 25


def test_recommendation_agent_contracts_preserve_resumable_state():
    request = RecommendationRequest(origin=RecommendationOrigin.ONBOARDING)
    message = RecommendationAgentMessage(
        role=RecommendationAgentMessageRole.USER,
        content="我喜欢侦探故事。",
    )
    session = RecommendationAgentSession(
        session_id="session-1",
        request=request,
        phase=RecommendationAgentPhase.SEARCHING,
        conversation=(message,),
        tool_call_count=1,
        observed_catalog_ids=("cam-jansen",),
    )
    observation = RecommendationAgentObservation(
        request=request,
        phase=session.phase,
        conversation=session.conversation,
        observed_catalog_ids=session.observed_catalog_ids,
        remaining_tool_calls=2,
    )
    decision = RecommendationAgentDecision(
        kind=RecommendationAgentDecisionKind.FINALIZE,
        message="推荐 Cam Jansen。",
        recommended_catalog_ids=("cam-jansen",),
    )
    reply = RecommendationAgentReply(
        session=session,
        message=decision.message,
        recommended_catalog_ids=decision.recommended_catalog_ids,
    )

    assert observation.remaining_tool_calls == 2
    assert reply.recommended_catalog_ids == ("cam-jansen",)


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (
            lambda: OperationalReadingBand(900, 700),
            "minimum_lexile",
        ),
        (
            lambda: BookDifficulty(900, 700),
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
        (
            lambda: BookCandidateMatch(
                candidate=BookCandidate(
                    catalog_id="candidate",
                    title_en="Candidate",
                    difficulty=BookDifficulty(700, 700),
                ),
                difficulty_distance=-1,
            ),
            "difficulty_distance",
        ),
        (
            lambda: RecommendationAgentSession(
                session_id="",
                request=RecommendationRequest(
                    origin=RecommendationOrigin.ONBOARDING
                ),
            ),
            "session_id",
        ),
        (
            lambda: RecommendationAgentObservation(
                request=RecommendationRequest(
                    origin=RecommendationOrigin.ONBOARDING
                ),
                phase=RecommendationAgentPhase.SEARCHING,
                conversation=(),
                observed_catalog_ids=(),
                remaining_tool_calls=-1,
            ),
            "remaining_tool_calls",
        ),
        (
            lambda: RecommendationAgentDecision(
                kind=RecommendationAgentDecisionKind.FINALIZE,
                message="完成",
            ),
            "between 1 and 3",
        ),
        (
            lambda: RecommendationAgentDecision(
                kind=RecommendationAgentDecisionKind.ASK_USER,
                message="请选择题材",
                tool_name="search_local_book_catalog",
            ),
            "unrelated action data",
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
