"""Stable data exchanged by book-recommendation application boundaries.

These contracts describe recommendation inputs, evidence, catalog results,
and observed outcomes. They do not calculate lookup density, search a catalog,
run an agent, persist a reader profile, or authorize a book switch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class RecommendationOrigin(StrEnum):
    """Why a recommendation conversation was started."""

    ONBOARDING = "onboarding"
    USER_REQUEST = "user_request"
    DIFFICULTY_ALERT = "difficulty_alert"


class ReadingPreference(StrEnum):
    """How much challenge the reader currently wants."""

    FLUENCY_FIRST = "fluency_first"
    BALANCED = "balanced"
    CHALLENGE_WELCOME = "challenge_welcome"


class RecommendationOutcomeKind(StrEnum):
    """Observed result after a recommended book was selected."""

    GOOD_FIT = "good_fit"
    DIFFICULTY_MISMATCH = "difficulty_mismatch"
    INTEREST_MISMATCH = "interest_mismatch"
    AVAILABILITY_PROBLEM = "availability_problem"
    UNKNOWN = "unknown"


class BookEntryKind(StrEnum):
    """Whether a catalog row represents one book or a broader work group."""

    BOOK = "book"
    SERIES = "series"
    COLLECTION = "collection"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class OperationalReadingBand:
    """Internal text-difficulty range used for recommendation.

    This is deliberately not named a reader Lexile measure: the application
    can infer a useful search range from behavior, but it does not administer
    a certified reader assessment.
    """

    minimum_lexile: int
    maximum_lexile: int
    confidence: float = 0.0
    evidence_source: str = ""

    def __post_init__(self) -> None:
        if self.minimum_lexile > self.maximum_lexile:
            raise ValueError("minimum_lexile must not exceed maximum_lexile")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True)
class BookDifficulty:
    """One exact Lexile value or an inclusive range."""

    minimum_lexile: int
    maximum_lexile: int

    def __post_init__(self) -> None:
        if self.minimum_lexile > self.maximum_lexile:
            raise ValueError("minimum_lexile must not exceed maximum_lexile")

    @property
    def exact_measure(self) -> int | None:
        """Return the measure only when the range represents one exact value."""
        if self.minimum_lexile == self.maximum_lexile:
            return self.minimum_lexile
        return None


@dataclass(frozen=True)
class BookSnapshot:
    """Minimal book state handed from the reading flow to recommendation."""

    book_id: str
    title: str
    title_zh: str = ""
    author: str = ""
    difficulty: BookDifficulty | None = None
    genres: tuple[str, ...] = ()
    progress: float | None = None

    def __post_init__(self) -> None:
        if self.progress is not None and not 0.0 <= self.progress <= 1.0:
            raise ValueError("progress must be between 0 and 1")


@dataclass(frozen=True)
class ReadingDifficultyEvidence:
    """Aggregated reading facts safe to hand to a recommendation task."""

    observed_word_count: int
    observed_chapter_count: int
    lookup_density: float
    unique_lookup_density: float = 0.0
    repeated_lookup_density: float = 0.0
    annotated_lookup_density: float = 0.0
    actual_annotation_density: float = 0.0
    annotation_target: int | None = None

    def __post_init__(self) -> None:
        numeric_values = (
            self.observed_word_count,
            self.observed_chapter_count,
            self.lookup_density,
            self.unique_lookup_density,
            self.repeated_lookup_density,
            self.annotated_lookup_density,
            self.actual_annotation_density,
        )
        if any(value < 0 for value in numeric_values):
            raise ValueError("reading difficulty evidence must not be negative")
        if self.annotation_target is not None and self.annotation_target < 0:
            raise ValueError("annotation_target must not be negative")


@dataclass(frozen=True)
class BookRecommendationHandoff:
    """Structured context created after the reader authorizes a book change."""

    current_book: BookSnapshot
    evidence: ReadingDifficultyEvidence
    target_band: OperationalReadingBand | None = None
    preserve_genre_by_default: bool = True


@dataclass(frozen=True)
class RecommendationRequest:
    """Goal and known preferences for one recommendation conversation."""

    origin: RecommendationOrigin
    preferred_genres: tuple[str, ...] = ()
    excluded_traits: tuple[str, ...] = ()
    reading_preference: ReadingPreference = ReadingPreference.BALANCED
    operational_band: OperationalReadingBand | None = None
    reference_books: tuple[BookSnapshot, ...] = ()
    handoff: BookRecommendationHandoff | None = None
    user_notes: str = ""


@dataclass(frozen=True)
class BookSearchQuery:
    """Catalog-neutral criteria selected during one agent search step."""

    lexile_min: int | None = None
    lexile_max: int | None = None
    categories: tuple[str, ...] = ()
    entry_kinds: tuple[BookEntryKind, ...] = ()
    excluded_ids: tuple[str, ...] = ()
    limit: int = 20

    def __post_init__(self) -> None:
        if (
            self.lexile_min is not None
            and self.lexile_max is not None
            and self.lexile_min > self.lexile_max
        ):
            raise ValueError("lexile_min must not exceed lexile_max")
        if not 1 <= self.limit <= 100:
            raise ValueError("limit must be between 1 and 100")


@dataclass(frozen=True)
class BookCandidate:
    """One normalized candidate returned by any book catalog adapter."""

    catalog_id: str
    title_en: str
    difficulty: BookDifficulty
    title_zh: str = ""
    author: str = ""
    entry_kind: BookEntryKind = BookEntryKind.UNKNOWN
    genres: tuple[str, ...] = ()
    raw_text: str = ""


@dataclass(frozen=True)
class BookCandidateMatch:
    """One candidate plus deterministic evidence used to rank it."""

    candidate: BookCandidate
    matched_genres: tuple[str, ...] = ()
    difficulty_distance: int = 0

    def __post_init__(self) -> None:
        if self.difficulty_distance < 0:
            raise ValueError("difficulty_distance must not be negative")


@dataclass(frozen=True)
class BookCandidateMatchResult:
    """Strict local-catalog matches returned to an agent-facing tool."""

    query: BookSearchQuery
    matches: tuple[BookCandidateMatch, ...] = ()

    @property
    def found(self) -> bool:
        """Whether the strict query produced at least one candidate."""
        return bool(self.matches)


@dataclass(frozen=True)
class RecommendationOutcome:
    """Reading evidence collected after the user selected a recommendation."""

    recommendation_id: str
    selected_book: BookSnapshot
    kind: RecommendationOutcomeKind = RecommendationOutcomeKind.UNKNOWN
    observed_word_count: int = 0
    completed_chapter_count: int = 0
    lookup_density: float = 0.0
    continued_reading: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.observed_word_count < 0 or self.completed_chapter_count < 0:
            raise ValueError("recommendation outcome counts must not be negative")
        if self.lookup_density < 0:
            raise ValueError("lookup_density must not be negative")
