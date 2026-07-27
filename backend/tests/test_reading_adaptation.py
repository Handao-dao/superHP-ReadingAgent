"""Decision-table tests for the pure reading-support adaptation policy."""

import pytest

from superhp_agent.application import (
    ReadingAdaptationAction,
    ReadingAdaptationPolicy,
    ReadingAdaptationState,
)
from superhp_agent.contracts import ReadingDifficultyEvidence


def _evidence(
    *,
    lookup_density: float,
    annotated_lookup_density: float = 0.0,
) -> ReadingDifficultyEvidence:
    return ReadingDifficultyEvidence(
        observed_word_count=6000,
        observed_chapter_count=3,
        lookup_density=lookup_density,
        annotated_lookup_density=annotated_lookup_density,
    )


def test_policy_preserves_state_until_observation_window_is_ready():
    state = ReadingAdaptationState(
        annotation_target=12,
        low_density_streak=1,
    )

    decision = ReadingAdaptationPolicy().decide(
        state,
        _evidence(lookup_density=20),
        window_ready=False,
    )

    assert decision.action is ReadingAdaptationAction.HOLD
    assert decision.next_state == state
    assert decision.reason == "window_not_ready"


def test_policy_increases_support_for_high_uncovered_lookup_density():
    decision = ReadingAdaptationPolicy().decide(
        ReadingAdaptationState(annotation_target=8),
        _evidence(lookup_density=11, annotated_lookup_density=2),
        window_ready=True,
    )

    assert decision.action is ReadingAdaptationAction.INCREASE
    assert decision.previous_target == 8
    assert decision.next_target == 10
    assert decision.uncovered_lookup_density == 9
    assert decision.next_state.low_density_streak == 0


@pytest.mark.parametrize("density", [3.0, 8.0])
def test_policy_holds_at_stable_band_boundaries_and_resets_streaks(density):
    decision = ReadingAdaptationPolicy().decide(
        ReadingAdaptationState(
            annotation_target=12,
            low_density_streak=1,
            max_target_high_density_streak=1,
        ),
        _evidence(lookup_density=density),
        window_ready=True,
    )

    assert decision.action is ReadingAdaptationAction.HOLD
    assert decision.next_target == 12
    assert decision.next_state.low_density_streak == 0
    assert decision.next_state.max_target_high_density_streak == 0


def test_policy_decreases_only_after_two_low_density_windows():
    policy = ReadingAdaptationPolicy()
    first = policy.decide(
        ReadingAdaptationState(annotation_target=12),
        _evidence(lookup_density=2.5),
        window_ready=True,
    )
    second = policy.decide(
        first.next_state,
        _evidence(lookup_density=1.5),
        window_ready=True,
    )

    assert first.action is ReadingAdaptationAction.HOLD
    assert first.next_state.low_density_streak == 1
    assert second.action is ReadingAdaptationAction.DECREASE
    assert second.next_target == 11
    assert second.next_state.low_density_streak == 0


def test_policy_never_decreases_below_automatic_minimum():
    decision = ReadingAdaptationPolicy().decide(
        ReadingAdaptationState(annotation_target=8),
        _evidence(lookup_density=0),
        window_ready=True,
    )

    assert decision.action is ReadingAdaptationAction.HOLD
    assert decision.next_target == 8
    assert decision.next_state.low_density_streak == 0
    assert decision.reason == "minimum_support_reached"


def test_policy_alerts_after_two_high_windows_at_maximum_support():
    policy = ReadingAdaptationPolicy()
    first = policy.decide(
        ReadingAdaptationState(annotation_target=20),
        _evidence(lookup_density=12),
        window_ready=True,
    )
    second = policy.decide(
        first.next_state,
        _evidence(lookup_density=10),
        window_ready=True,
    )
    third = policy.decide(
        second.next_state,
        _evidence(lookup_density=11),
        window_ready=True,
    )

    assert first.action is ReadingAdaptationAction.HOLD
    assert first.next_state.max_target_high_density_streak == 1
    assert second.action is ReadingAdaptationAction.DIFFICULTY_ALERT
    assert second.next_state.max_target_high_density_streak == 2
    assert third.action is ReadingAdaptationAction.HOLD
    assert third.reason == "difficulty_alert_already_reached"


def test_policy_does_not_treat_lookups_on_annotated_words_as_missing_coverage():
    decision = ReadingAdaptationPolicy().decide(
        ReadingAdaptationState(annotation_target=10),
        _evidence(lookup_density=12, annotated_lookup_density=5),
        window_ready=True,
    )

    assert decision.uncovered_lookup_density == 7
    assert decision.action is ReadingAdaptationAction.HOLD
    assert decision.next_target == 10


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {"low_density_threshold": 5, "high_density_threshold": 5},
            "high_density_threshold",
        ),
        ({"increase_step": 0}, "adaptation steps"),
        ({"low_windows_before_decrease": 0}, "low_windows_before_decrease"),
    ],
)
def test_policy_rejects_invalid_configuration(kwargs, message):
    with pytest.raises(ValueError, match=message):
        ReadingAdaptationPolicy(**kwargs)


def test_policy_rejects_target_outside_automatic_range():
    with pytest.raises(ValueError, match="automatic policy range"):
        ReadingAdaptationPolicy().decide(
            ReadingAdaptationState(annotation_target=7),
            _evidence(lookup_density=5),
            window_ready=True,
        )
