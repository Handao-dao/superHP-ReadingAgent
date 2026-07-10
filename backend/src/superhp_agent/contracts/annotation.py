"""Stable annotation data exchanged across backend layers.

These classes carry outcomes and degradation metadata only. They do not call
models, validate markers, emit events, or decide whether an artifact is saved.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AnnotationItem:
    """One learning item extracted from a validated annotation result."""

    word: str
    translation: str
    context: str
    pos: str = "other"


@dataclass(frozen=True)
class ServiceIssue:
    """Machine-readable degradation information safe to pass across layers.

    ``category`` separates Provider failures from content validation failures;
    ``code`` is the stable value for program logic, while ``message`` is only
    display copy and may change without breaking consumers.
    """

    category: str
    code: str
    message: str
    chunk_index: int | None = None


@dataclass(frozen=True)
class AnnotationChunkOutcome:
    """Validated model text or the original-text fallback for one chunk."""

    index: int
    text: str
    issue: ServiceIssue | None = None

    @property
    def degraded(self) -> bool:
        return self.issue is not None


@dataclass(frozen=True)
class AnnotationResult:
    """Complete readable text plus per-chunk validation and issue counts.

    ``annotated_text`` may mix validated annotations with original-text
    fallbacks. Runtime uses the counters to distinguish a useful mixed result
    from a fully degraded result that must not be persisted as an annotation.
    """

    annotated_text: str
    vocabulary: list[AnnotationItem]
    validated_chunk_count: int
    total_chunk_count: int
    issues: list[ServiceIssue] = field(default_factory=list)

    @property
    def fully_degraded(self) -> bool:
        """Whether every model chunk fell back to its original source text."""
        return self.total_chunk_count > 0 and self.validated_chunk_count == 0
