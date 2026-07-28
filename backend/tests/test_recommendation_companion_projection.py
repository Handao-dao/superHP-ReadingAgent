"""Tests for the side-effect-free recommendation-to-companion projection."""

from dataclasses import replace

import pytest

from superhp_agent.application import (
    RecommendationCompanionProjectionError,
    legacy_recommendation_episode_id,
    legacy_recommendation_message_id,
    project_recommendation_session,
)
from superhp_agent.contracts import (
    BookRecommendationHandoff,
    BookSnapshot,
    ReadingCompanionEpisodeEndReason,
    ReadingCompanionEpisodeState,
    ReadingCompanionEpisodeTrigger,
    ReadingCompanionSessionStatus,
    ReadingDifficultyEvidence,
    RecommendationAgentMessage,
    RecommendationAgentMessageRole,
    RecommendationAgentPhase,
    RecommendationAgentSession,
    RecommendationOrigin,
    RecommendationRequest,
)


def message(
    role: RecommendationAgentMessageRole,
    content: str,
) -> RecommendationAgentMessage:
    return RecommendationAgentMessage(role=role, content=content)


def test_onboarding_session_projects_to_one_active_episode():
    source = RecommendationAgentSession(
        session_id="session-1",
        request=RecommendationRequest(
            origin=RecommendationOrigin.ONBOARDING
        ),
        phase=RecommendationAgentPhase.AWAITING_USER,
        conversation=(
            message(
                RecommendationAgentMessageRole.ASSISTANT,
                "你喜欢哪类故事？",
            ),
        ),
    )

    projection = project_recommendation_session(source)

    assert projection.session.session_id == "session-1"
    assert projection.session.reader_key == "default"
    assert projection.session.status is ReadingCompanionSessionStatus.ACTIVE
    assert projection.episode.trigger is (
        ReadingCompanionEpisodeTrigger.ONBOARDING
    )
    assert projection.episode.state is ReadingCompanionEpisodeState.ACTIVE
    assert projection.session.active_episode_id == projection.episode.episode_id
    assert projection.message_ids == (
        "legacy-recommendation:session-1:message:0",
    )
    assert projection.episode.start_message_id == projection.message_ids[0]


def test_difficulty_handoff_uses_current_context_epoch_and_book():
    request = RecommendationRequest(
        origin=RecommendationOrigin.DIFFICULTY_ALERT,
        handoff=BookRecommendationHandoff(
            current_book=BookSnapshot(
                book_id="hp01",
                title="Harry Potter",
            ),
            evidence=ReadingDifficultyEvidence(
                observed_word_count=7200,
                observed_chapter_count=3,
                lookup_density=12.0,
            ),
        ),
    )
    source = RecommendationAgentSession(
        session_id="session-1",
        request=request,
        phase=RecommendationAgentPhase.AWAITING_USER,
        conversation=(
            message(
                RecommendationAgentMessageRole.ASSISTANT,
                "此前的初次推荐。",
            ),
            message(
                RecommendationAgentMessageRole.USER,
                "我选择了这本书。",
            ),
            message(
                RecommendationAgentMessageRole.USER,
                "现在我想换一本更轻松的。",
            ),
            message(
                RecommendationAgentMessageRole.ASSISTANT,
                "我会结合最近的阅读情况。",
            ),
        ),
        context_start_index=2,
    )

    projection = project_recommendation_session(
        source,
        reader_key="single-reader",
    )

    assert projection.session.reader_key == "single-reader"
    assert projection.episode.trigger is (
        ReadingCompanionEpisodeTrigger.DIFFICULTY_ALERT
    )
    assert projection.episode.book_id == "hp01"
    assert projection.episode.start_message_id == (
        "legacy-recommendation:session-1:message:2"
    )
    assert projection.episode.episode_id.endswith(":episode:2")
    assert len(projection.message_ids) == 4


def test_selected_book_completes_episode_but_not_companion_session():
    source = RecommendationAgentSession(
        session_id="session-1",
        request=RecommendationRequest(
            origin=RecommendationOrigin.ONBOARDING
        ),
        phase=RecommendationAgentPhase.COMPLETED,
        conversation=(
            message(
                RecommendationAgentMessageRole.USER,
                "我选择 Cam Jansen。",
            ),
            message(
                RecommendationAgentMessageRole.ASSISTANT,
                "已经为你确认。",
            ),
        ),
        recommended_catalog_ids=("cam-jansen",),
        selected_catalog_id="cam-jansen",
    )

    projection = project_recommendation_session(source)

    assert projection.episode.state is ReadingCompanionEpisodeState.COMPLETED
    assert projection.episode.end_reason is (
        ReadingCompanionEpisodeEndReason.BOOK_SELECTED
    )
    assert projection.episode.end_message_id.endswith(":message:1")
    assert projection.session.status is ReadingCompanionSessionStatus.ACTIVE
    assert projection.session.active_episode_id == ""


def test_legacy_failed_phase_abandons_only_the_episode():
    source = RecommendationAgentSession(
        session_id="session-1",
        request=RecommendationRequest(
            origin=RecommendationOrigin.USER_REQUEST
        ),
        phase=RecommendationAgentPhase.FAILED,
        conversation=(
            message(
                RecommendationAgentMessageRole.ASSISTANT,
                "旧版本中的不可恢复错误。",
            ),
        ),
        error_code="legacy_failure",
    )

    projection = project_recommendation_session(source)

    assert projection.episode.state is ReadingCompanionEpisodeState.ABANDONED
    assert projection.episode.end_reason is (
        ReadingCompanionEpisodeEndReason.UNRECOVERABLE_ERROR
    )
    assert projection.session.status is ReadingCompanionSessionStatus.ACTIVE
    assert projection.session.active_episode_id == ""


def test_empty_recoverable_session_uses_a_stable_start_boundary():
    source = RecommendationAgentSession(
        session_id="session-1",
        request=RecommendationRequest(
            origin=RecommendationOrigin.ONBOARDING
        ),
        error_code="model_error",
    )

    first = project_recommendation_session(source)
    second = project_recommendation_session(source)

    assert first == second
    assert first.message_ids == ()
    assert first.episode.start_message_id == (
        "legacy-recommendation:session-1:message:0"
    )
    assert first.episode.state is ReadingCompanionEpisodeState.ACTIVE


def test_difficulty_projection_rejects_missing_handoff_book():
    source = RecommendationAgentSession(
        session_id="session-1",
        request=RecommendationRequest(
            origin=RecommendationOrigin.DIFFICULTY_ALERT
        ),
    )

    with pytest.raises(
        RecommendationCompanionProjectionError,
        match="requires a handoff current book",
    ):
        project_recommendation_session(source)


def test_legacy_ids_are_stable_and_validate_boundaries():
    assert legacy_recommendation_episode_id("session", 3) == (
        "legacy-recommendation:session:episode:3"
    )
    assert legacy_recommendation_message_id("session", 7) == (
        "legacy-recommendation:session:message:7"
    )

    with pytest.raises(ValueError, match="message_index"):
        legacy_recommendation_message_id("session", -1)
    with pytest.raises(ValueError, match="context_start_index"):
        legacy_recommendation_episode_id("session", -1)


def test_projection_does_not_mutate_source_session():
    source = RecommendationAgentSession(
        session_id="session-1",
        request=RecommendationRequest(
            origin=RecommendationOrigin.ONBOARDING
        ),
    )
    expected = replace(source)

    project_recommendation_session(source)

    assert source == expected
