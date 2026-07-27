"""Pure rules for per-book English annotation support targets."""

from dataclasses import dataclass

DEFAULT_ANNOTATION_TARGET = 8
MIN_ANNOTATION_TARGET = 1
MAX_ANNOTATION_TARGET = 20
TARGET_CHANGE_COOLDOWN_CHAPTERS = 3


def validate_annotation_target(annotation_target: int) -> int:
    """Return a valid integer target or reject unsafe implicit coercion."""
    if isinstance(annotation_target, bool) or not isinstance(
        annotation_target,
        int,
    ):
        raise ValueError("annotation_target must be an integer")
    if not MIN_ANNOTATION_TARGET <= annotation_target <= MAX_ANNOTATION_TARGET:
        raise ValueError(
            "annotation_target must be between "
            f"{MIN_ANNOTATION_TARGET} and {MAX_ANNOTATION_TARGET}"
        )
    return annotation_target


@dataclass(frozen=True)
class ReadingSupportState:
    """Persisted per-book state surrounding the current support target."""

    annotation_target: int = DEFAULT_ANNOTATION_TARGET
    low_density_streak: int = 0
    max_target_high_density_streak: int = 0
    last_evaluated_chapter_id: str = ""
    cooldown_chapters_remaining: int = 0
    last_decision: str = ""
    last_uncovered_lookup_density: float = 0.0
    updated_at: str = ""

    def __post_init__(self) -> None:
        validate_annotation_target(self.annotation_target)
        counters = (
            self.low_density_streak,
            self.max_target_high_density_streak,
            self.cooldown_chapters_remaining,
        )
        if any(counter < 0 for counter in counters):
            raise ValueError("reading support counters must not be negative")
        if self.last_uncovered_lookup_density < 0:
            raise ValueError(
                "last_uncovered_lookup_density must not be negative"
            )
