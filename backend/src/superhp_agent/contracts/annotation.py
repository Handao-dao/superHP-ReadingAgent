"""Stable results exchanged by annotation profiles, services, and runtime."""

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
    """Machine-readable degradation information safe to pass across layers."""

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
    """Complete annotation text plus structured degradation information."""

    annotated_text: str
    vocabulary: list[AnnotationItem]
    validated_chunk_count: int
    total_chunk_count: int
    issues: list[ServiceIssue] = field(default_factory=list)

    @property
    def fully_degraded(self) -> bool:
        return self.total_chunk_count > 0 and self.validated_chunk_count == 0
