"""Evaluate the latest three completed chapters and apply safe target changes.

Only ``increase`` and ``decrease`` decisions change ``annotation_target``.
Callers may disable writes explicitly for shadow-mode tests and diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass

from superhp_agent.application.reading_adaptation import (
    ReadingAdaptationAction,
    ReadingAdaptationDecision,
    ReadingAdaptationPolicy,
    ReadingAdaptationState,
)
from superhp_agent.contracts import (
    ChapterReadingCheckpoint,
    ReadingDifficultyEvidence,
)
from superhp_agent.domain.reading_metrics import density_per_300
from superhp_agent.domain.reading_support import (
    TARGET_CHANGE_COOLDOWN_CHAPTERS,
    ReadingSupportState,
)
from superhp_agent.ports.events import EventLogger
from superhp_agent.ports.repositories import (
    ChapterReadingCheckpointRepository,
    ReadingSupportRepository,
)

ADAPTATION_WINDOW_CHAPTERS = 3


@dataclass(frozen=True)
class ReadingAdaptationWindow:
    """The latest three chapter checkpoints aggregated for one book."""

    book_id: str
    checkpoints: tuple[ChapterReadingCheckpoint, ...]
    evidence: ReadingDifficultyEvidence

    @property
    def chapter_ids(self) -> tuple[str, ...]:
        return tuple(
            checkpoint.chapter_id for checkpoint in self.checkpoints
        )


@dataclass(frozen=True)
class ReadingAdaptationEvaluation:
    """One persisted policy evaluation or cooldown observation."""

    window: ReadingAdaptationWindow
    decision: ReadingAdaptationDecision | None
    reason: str
    cooldown_chapters_remaining: int
    active_target: int
    target_changed: bool
    shadow_mode: bool


class ReadingAdaptationEvaluator:
    """Build one sliding window per new chapter and persist per-book state."""

    def __init__(
        self,
        checkpoint_repository: ChapterReadingCheckpointRepository,
        support_repository: ReadingSupportRepository,
        *,
        policy: ReadingAdaptationPolicy | None = None,
        apply_target_changes: bool = True,
    ):
        self.checkpoint_repository = checkpoint_repository
        self.support_repository = support_repository
        self.policy = policy or ReadingAdaptationPolicy()
        self.apply_target_changes = bool(apply_target_changes)

    def evaluate_book(
        self,
        book_id: str,
    ) -> ReadingAdaptationEvaluation | None:
        checkpoints = self.checkpoint_repository.latest_for_book(
            book_id,
            limit=ADAPTATION_WINDOW_CHAPTERS,
        )
        if not checkpoints:
            return None

        support_state = self.support_repository.get_state(book_id)
        newest = checkpoints[-1]
        if (
            support_state.last_evaluated_chapter_id
            == newest.chapter_id
        ):
            return None

        cooldown_remaining = support_state.cooldown_chapters_remaining
        if cooldown_remaining > 0:
            matches_current_target = (
                newest.annotation_target == support_state.annotation_target
            )
            if matches_current_target:
                cooldown_remaining -= 1
            if (
                len(checkpoints) < ADAPTATION_WINDOW_CHAPTERS
                or cooldown_remaining > 0
                or not matches_current_target
            ):
                reason = (
                    "adjustment_cooldown"
                    if matches_current_target
                    else "cooldown_waiting_for_matching_target"
                )
                self.support_repository.save_evaluation_state(
                    book_id,
                    _next_support_state(
                        support_state,
                        newest_chapter_id=newest.chapter_id,
                        cooldown_chapters_remaining=cooldown_remaining,
                        last_decision=reason,
                    ),
                )
                if len(checkpoints) < ADAPTATION_WINDOW_CHAPTERS:
                    return None
                window = _build_window(
                    book_id,
                    checkpoints,
                    annotation_target=support_state.annotation_target,
                )
                return ReadingAdaptationEvaluation(
                    window=window,
                    decision=None,
                    reason=reason,
                    cooldown_chapters_remaining=cooldown_remaining,
                    active_target=support_state.annotation_target,
                    target_changed=False,
                    shadow_mode=not self.apply_target_changes,
                )

        if len(checkpoints) < ADAPTATION_WINDOW_CHAPTERS:
            return None
        window = _build_window(
            book_id,
            checkpoints,
            annotation_target=support_state.annotation_target,
        )
        decision = self.policy.decide(
            ReadingAdaptationState(
                annotation_target=support_state.annotation_target,
                low_density_streak=support_state.low_density_streak,
                max_target_high_density_streak=(
                    support_state.max_target_high_density_streak
                ),
            ),
            window.evidence,
            window_ready=True,
        )
        target_changed = (
            self.apply_target_changes
            and decision.action
            in {
                ReadingAdaptationAction.INCREASE,
                ReadingAdaptationAction.DECREASE,
            }
            and decision.next_target != support_state.annotation_target
        )
        active_target = (
            decision.next_target
            if target_changed
            else support_state.annotation_target
        )
        cooldown_remaining = (
            TARGET_CHANGE_COOLDOWN_CHAPTERS if target_changed else 0
        )
        decision_prefix = (
            "applied"
            if target_changed
            else "shadow"
            if not self.apply_target_changes
            else "observed"
        )
        next_state = ReadingSupportState(
            annotation_target=active_target,
            low_density_streak=decision.next_state.low_density_streak,
            max_target_high_density_streak=(
                decision.next_state.max_target_high_density_streak
            ),
            last_evaluated_chapter_id=newest.chapter_id,
            cooldown_chapters_remaining=cooldown_remaining,
            last_decision=f"{decision_prefix}:{decision.action.value}",
            last_uncovered_lookup_density=(
                decision.uncovered_lookup_density
            ),
        )
        self.support_repository.save_evaluation_state(book_id, next_state)
        return ReadingAdaptationEvaluation(
            window=window,
            decision=decision,
            reason=(
                "target_updated"
                if target_changed
                else "shadow_decision"
                if not self.apply_target_changes
                else "decision_recorded"
            ),
            cooldown_chapters_remaining=cooldown_remaining,
            active_target=active_target,
            target_changed=target_changed,
            shadow_mode=not self.apply_target_changes,
        )

    def evaluate_and_log(
        self,
        book_id: str,
        event_logger: EventLogger | None,
    ) -> None:
        """Evaluate once and emit an audit event describing any target write."""
        evaluation = self.evaluate_book(book_id)
        if evaluation is None or event_logger is None:
            return
        decision = evaluation.decision
        current_target = evaluation.window.evidence.annotation_target
        uncovered_lookup_density = (
            decision.uncovered_lookup_density
            if decision is not None
            else round(
                max(
                    0.0,
                    evaluation.window.evidence.lookup_density
                    - evaluation.window.evidence.annotated_lookup_density,
                ),
                2,
            )
        )
        event_logger.log_event(
            "reading_adaptation_evaluated",
            book_id=book_id,
            chapter_ids=list(evaluation.window.chapter_ids),
            lookup_density=evaluation.window.evidence.lookup_density,
            annotated_lookup_density=(
                evaluation.window.evidence.annotated_lookup_density
            ),
            uncovered_lookup_density=uncovered_lookup_density,
            current_target=current_target,
            proposed_target=(
                decision.next_target
                if decision is not None
                else current_target
            ),
            active_target=evaluation.active_target,
            target_changed=evaluation.target_changed,
            action=(
                decision.action.value if decision is not None else "hold"
            ),
            reason=evaluation.reason,
            cooldown_chapters_remaining=(
                evaluation.cooldown_chapters_remaining
            ),
            shadow_mode=evaluation.shadow_mode,
        )


def _build_window(
    book_id: str,
    checkpoints: tuple[ChapterReadingCheckpoint, ...],
    *,
    annotation_target: int,
) -> ReadingAdaptationWindow:
    word_count = sum(checkpoint.word_count for checkpoint in checkpoints)
    lookup_count = sum(checkpoint.lookup_count for checkpoint in checkpoints)
    annotated_lookup_count = sum(
        checkpoint.annotated_lookup_count for checkpoint in checkpoints
    )
    evidence = ReadingDifficultyEvidence(
        observed_word_count=word_count,
        observed_chapter_count=len(checkpoints),
        lookup_density=density_per_300(lookup_count, word_count),
        annotated_lookup_density=density_per_300(
            annotated_lookup_count,
            word_count,
        ),
        annotation_target=annotation_target,
    )
    return ReadingAdaptationWindow(
        book_id=book_id,
        checkpoints=checkpoints,
        evidence=evidence,
    )


def _next_support_state(
    current: ReadingSupportState,
    *,
    newest_chapter_id: str,
    cooldown_chapters_remaining: int,
    last_decision: str,
) -> ReadingSupportState:
    return ReadingSupportState(
        annotation_target=current.annotation_target,
        low_density_streak=current.low_density_streak,
        max_target_high_density_streak=(
            current.max_target_high_density_streak
        ),
        last_evaluated_chapter_id=newest_chapter_id,
        cooldown_chapters_remaining=cooldown_chapters_remaining,
        last_decision=last_decision,
        last_uncovered_lookup_density=(
            current.last_uncovered_lookup_density
        ),
    )
