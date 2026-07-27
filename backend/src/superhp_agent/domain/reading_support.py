"""Pure rules for per-book English annotation support targets."""

DEFAULT_ANNOTATION_TARGET = 8
MIN_ANNOTATION_TARGET = 1
MAX_ANNOTATION_TARGET = 20


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
