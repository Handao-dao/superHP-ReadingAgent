"""Deterministic policy for adapting per-book annotation support.

This module contains no storage, Corpus, transport, or model calls. It turns one
completed observation window plus persisted counters into an explicit decision;
later orchestration code is responsible for loading and saving that state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from superhp_agent.contracts import ReadingDifficultyEvidence
from superhp_agent.domain.reading_support import validate_annotation_target


class ReadingAdaptationAction(StrEnum):
    """Actions the orchestration layer may apply after one ready window."""

    HOLD = "hold"
    INCREASE = "increase"
    DECREASE = "decrease"
    DIFFICULTY_ALERT = "difficulty_alert"


@dataclass(frozen=True)
class ReadingAdaptationState:
    """Minimal cross-window state required to provide hysteresis."""

    annotation_target: int
    low_density_streak: int = 0
    max_target_high_density_streak: int = 0

    def __post_init__(self) -> None:
        validate_annotation_target(self.annotation_target)
        if self.low_density_streak < 0:
            raise ValueError("low_density_streak must not be negative")
        if self.max_target_high_density_streak < 0:
            raise ValueError(
                "max_target_high_density_streak must not be negative"
            )


@dataclass(frozen=True)
class ReadingAdaptationDecision:
    """Pure policy output, including the state to persist for the next window."""

    action: ReadingAdaptationAction
    previous_target: int
    next_state: ReadingAdaptationState
    uncovered_lookup_density: float
    reason: str

    @property
    def next_target(self) -> int:
        return self.next_state.annotation_target


@dataclass(frozen=True)
class ReadingAdaptationPolicy:
    """Apply the first conservative support-adjustment decision table."""

    minimum_target: int = 8
    maximum_target: int = 20
    high_density_threshold: float = 8.0
    low_density_threshold: float = 3.0
    increase_step: int = 2
    decrease_step: int = 1
    low_windows_before_decrease: int = 2
    max_high_windows_before_alert: int = 2

    def __post_init__(self) -> None:
        validate_annotation_target(self.minimum_target)
        validate_annotation_target(self.maximum_target)
        if self.minimum_target > self.maximum_target:
            raise ValueError("minimum_target must not exceed maximum_target")
        if self.low_density_threshold < 0:
            raise ValueError("low_density_threshold must not be negative")
        if self.high_density_threshold <= self.low_density_threshold:
            raise ValueError(
                "high_density_threshold must exceed low_density_threshold"
            )
        if self.increase_step < 1 or self.decrease_step < 1:
            raise ValueError("adaptation steps must be positive")
        if self.low_windows_before_decrease < 1:
            raise ValueError("low_windows_before_decrease must be positive")
        if self.max_high_windows_before_alert < 1:
            raise ValueError("max_high_windows_before_alert must be positive")

    def decide(
        self,
        state: ReadingAdaptationState,
        evidence: ReadingDifficultyEvidence,
        *,
        window_ready: bool,
    ) -> ReadingAdaptationDecision:
        """Return one decision without mutating state or external resources."""
        self._validate_current_target(state.annotation_target)
        uncovered_density = round(
            max(
                0.0,
                evidence.lookup_density - evidence.annotated_lookup_density,
            ),
            2,
        )

        if not window_ready:
            return self._decision(
                ReadingAdaptationAction.HOLD,
                state,
                state,
                uncovered_density,
                "window_not_ready",
            )
        if uncovered_density > self.high_density_threshold:
            return self._handle_high_density(state, uncovered_density)
        if uncovered_density < self.low_density_threshold:
            return self._handle_low_density(state, uncovered_density)

        return self._decision(
            ReadingAdaptationAction.HOLD,
            state,
            ReadingAdaptationState(annotation_target=state.annotation_target),
            uncovered_density,
            "density_within_stable_band",
        )

    def _handle_high_density(
        self,
        state: ReadingAdaptationState,
        uncovered_density: float,
    ) -> ReadingAdaptationDecision:
        if state.annotation_target < self.maximum_target:
            next_target = min(
                self.maximum_target,
                state.annotation_target + self.increase_step,
            )
            return self._decision(
                ReadingAdaptationAction.INCREASE,
                state,
                ReadingAdaptationState(annotation_target=next_target),
                uncovered_density,
                "uncovered_lookup_density_high",
            )

        if (
            state.max_target_high_density_streak
            >= self.max_high_windows_before_alert
        ):
            return self._decision(
                ReadingAdaptationAction.HOLD,
                state,
                state,
                uncovered_density,
                "difficulty_alert_already_reached",
            )

        high_streak = state.max_target_high_density_streak + 1
        next_state = ReadingAdaptationState(
            annotation_target=state.annotation_target,
            max_target_high_density_streak=high_streak,
        )
        if high_streak >= self.max_high_windows_before_alert:
            return self._decision(
                ReadingAdaptationAction.DIFFICULTY_ALERT,
                state,
                next_state,
                uncovered_density,
                "maximum_support_still_insufficient",
            )
        return self._decision(
            ReadingAdaptationAction.HOLD,
            state,
            next_state,
            uncovered_density,
            "confirming_difficulty_at_maximum_support",
        )

    def _handle_low_density(
        self,
        state: ReadingAdaptationState,
        uncovered_density: float,
    ) -> ReadingAdaptationDecision:
        if state.annotation_target <= self.minimum_target:
            return self._decision(
                ReadingAdaptationAction.HOLD,
                state,
                ReadingAdaptationState(annotation_target=state.annotation_target),
                uncovered_density,
                "minimum_support_reached",
            )

        low_streak = state.low_density_streak + 1
        if low_streak >= self.low_windows_before_decrease:
            next_target = max(
                self.minimum_target,
                state.annotation_target - self.decrease_step,
            )
            return self._decision(
                ReadingAdaptationAction.DECREASE,
                state,
                ReadingAdaptationState(annotation_target=next_target),
                uncovered_density,
                "sustained_low_lookup_density",
            )

        return self._decision(
            ReadingAdaptationAction.HOLD,
            state,
            ReadingAdaptationState(
                annotation_target=state.annotation_target,
                low_density_streak=low_streak,
            ),
            uncovered_density,
            "confirming_low_lookup_density",
        )

    def _validate_current_target(self, annotation_target: int) -> None:
        if not self.minimum_target <= annotation_target <= self.maximum_target:
            raise ValueError(
                "current annotation_target must be within the automatic "
                f"policy range {self.minimum_target}..{self.maximum_target}"
            )

    @staticmethod
    def _decision(
        action: ReadingAdaptationAction,
        previous_state: ReadingAdaptationState,
        next_state: ReadingAdaptationState,
        uncovered_lookup_density: float,
        reason: str,
    ) -> ReadingAdaptationDecision:
        return ReadingAdaptationDecision(
            action=action,
            previous_target=previous_state.annotation_target,
            next_state=next_state,
            uncovered_lookup_density=uncovered_lookup_density,
            reason=reason,
        )
