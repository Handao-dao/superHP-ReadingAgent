"""Compatibility projection from the current recommendation conversation.

The running recommendation Loop and its SQLite payload remain unchanged. This
module only gives future reading-companion code a deterministic Session and
Episode view of that legacy state; it performs no persistence or model calls.
"""

from __future__ import annotations

from dataclasses import dataclass

from superhp_agent.contracts import (
    ReadingCompanionEpisode,
    ReadingCompanionEpisodeEndReason,
    ReadingCompanionEpisodeState,
    ReadingCompanionEpisodeTrigger,
    ReadingCompanionSession,
    RecommendationAgentPhase,
    RecommendationAgentSession,
    RecommendationOrigin,
)


class RecommendationCompanionProjectionError(ValueError):
    """Raised when legacy recommendation state lacks a safe episode boundary."""


@dataclass(frozen=True)
class RecommendationCompanionProjection:
    """Long-lived companion view plus deterministic legacy message ids."""

    session: ReadingCompanionSession
    episode: ReadingCompanionEpisode
    message_ids: tuple[str, ...]


def project_recommendation_session(
    source: RecommendationAgentSession,
    *,
    reader_key: str = "default",
) -> RecommendationCompanionProjection:
    """Project one current recommendation context epoch into one episode."""
    trigger = _episode_trigger(source.request.origin)
    book_id = _episode_book_id(source)
    if (
        trigger is ReadingCompanionEpisodeTrigger.DIFFICULTY_ALERT
        and not book_id
    ):
        raise RecommendationCompanionProjectionError(
            "difficulty recommendation requires a handoff current book"
        )

    message_ids = tuple(
        legacy_recommendation_message_id(source.session_id, index)
        for index in range(len(source.conversation))
    )
    start_message_id = legacy_recommendation_message_id(
        source.session_id,
        source.context_start_index,
    )
    episode_state, end_reason = _episode_completion(source)
    episode_id = legacy_recommendation_episode_id(
        source.session_id,
        source.context_start_index,
    )
    end_message_id = ""
    if episode_state is not ReadingCompanionEpisodeState.ACTIVE:
        end_index = max(source.context_start_index, len(source.conversation) - 1)
        end_message_id = legacy_recommendation_message_id(
            source.session_id,
            end_index,
        )

    episode = ReadingCompanionEpisode(
        episode_id=episode_id,
        session_id=source.session_id,
        trigger=trigger,
        start_message_id=start_message_id,
        state=episode_state,
        book_id=book_id,
        end_message_id=end_message_id,
        end_reason=end_reason,
    )
    companion_session = ReadingCompanionSession(
        session_id=source.session_id,
        reader_key=reader_key,
        active_episode_id=(
            episode_id
            if episode_state is ReadingCompanionEpisodeState.ACTIVE
            else ""
        ),
    )
    return RecommendationCompanionProjection(
        session=companion_session,
        episode=episode,
        message_ids=message_ids,
    )


def legacy_recommendation_episode_id(
    session_id: str,
    context_start_index: int,
) -> str:
    """Return the stable episode id for one legacy context epoch."""
    if not session_id.strip():
        raise ValueError("session_id must not be empty")
    if context_start_index < 0:
        raise ValueError("context_start_index must not be negative")
    return f"legacy-recommendation:{session_id}:episode:{context_start_index}"


def legacy_recommendation_message_id(
    session_id: str,
    message_index: int,
) -> str:
    """Return a stable cursor for one legacy message or empty start boundary."""
    if not session_id.strip():
        raise ValueError("session_id must not be empty")
    if message_index < 0:
        raise ValueError("message_index must not be negative")
    return f"legacy-recommendation:{session_id}:message:{message_index}"


def _episode_trigger(
    origin: RecommendationOrigin,
) -> ReadingCompanionEpisodeTrigger:
    return {
        RecommendationOrigin.ONBOARDING: (
            ReadingCompanionEpisodeTrigger.ONBOARDING
        ),
        RecommendationOrigin.USER_REQUEST: (
            ReadingCompanionEpisodeTrigger.USER_REQUEST
        ),
        RecommendationOrigin.DIFFICULTY_ALERT: (
            ReadingCompanionEpisodeTrigger.DIFFICULTY_ALERT
        ),
    }[origin]


def _episode_book_id(source: RecommendationAgentSession) -> str:
    handoff = source.request.handoff
    if handoff is None:
        return ""
    return handoff.current_book.book_id


def _episode_completion(
    source: RecommendationAgentSession,
) -> tuple[
    ReadingCompanionEpisodeState,
    ReadingCompanionEpisodeEndReason | None,
]:
    if source.phase is RecommendationAgentPhase.COMPLETED:
        reason = (
            ReadingCompanionEpisodeEndReason.BOOK_SELECTED
            if source.selected_catalog_id
            else ReadingCompanionEpisodeEndReason.USER_ENDED
        )
        return ReadingCompanionEpisodeState.COMPLETED, reason
    if source.phase is RecommendationAgentPhase.FAILED:
        return (
            ReadingCompanionEpisodeState.ABANDONED,
            ReadingCompanionEpisodeEndReason.UNRECOVERABLE_ERROR,
        )
    return ReadingCompanionEpisodeState.ACTIVE, None
