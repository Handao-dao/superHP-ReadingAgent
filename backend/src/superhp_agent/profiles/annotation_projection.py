"""Project model-proposed glosses onto immutable source text.

The model supplies only candidate spans and short location anchors. This module
locates trustworthy candidates and rebuilds the annotated passage from the
original source, so rejected candidates never force unrelated text to fall
back and model-written prose is never persisted.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from superhp_agent.contracts.annotation import AnnotationCandidate, AnnotationItem

_RESERVED_MARKER_CHARS = frozenset("|[]")
_POS_ALIASES = {
    "n": "noun",
    "v": "verb",
    "adj": "adjective",
    "adv": "adverb",
}


@dataclass(frozen=True)
class CandidateRejection:
    """Why one candidate could not be applied without guessing."""

    candidate_index: int
    code: str


@dataclass(frozen=True)
class AnnotationProjection:
    """Source-derived annotated text plus accepted and rejected candidates."""

    annotated_text: str
    items: list[AnnotationItem] = field(default_factory=list)
    rejections: list[CandidateRejection] = field(default_factory=list)


@dataclass(frozen=True)
class _LocatedCandidate:
    start: int
    end: int
    candidate: AnnotationCandidate
    pos: str


def project_annotation_candidates(
    source_text: str,
    candidates: list[AnnotationCandidate],
    *,
    allowed_pos: frozenset[str],
) -> AnnotationProjection:
    """Apply only uniquely located, non-overlapping candidates to source text."""

    located: list[_LocatedCandidate] = []
    rejections: list[CandidateRejection] = []

    for candidate_index, candidate in enumerate(candidates, start=1):
        rejection_code = _candidate_shape_error(candidate)
        if rejection_code is not None:
            rejections.append(CandidateRejection(candidate_index, rejection_code))
            continue

        source_positions = _source_positions(source_text, candidate.source)
        if not source_positions:
            rejections.append(CandidateRejection(candidate_index, "source_not_found"))
            continue
        if len(source_positions) == 1:
            positions = source_positions
        else:
            positions = _anchor_matching_positions(
                source_text,
                candidate,
                source_positions,
            )
        if not positions:
            rejections.append(CandidateRejection(candidate_index, "anchor_mismatch"))
            continue
        if len(positions) > 1:
            rejections.append(CandidateRejection(candidate_index, "ambiguous_source"))
            continue

        start = positions[0]
        end = start + len(candidate.source)
        if any(start < item.end and end > item.start for item in located):
            rejections.append(CandidateRejection(candidate_index, "overlapping_source"))
            continue

        located.append(
            _LocatedCandidate(
                start=start,
                end=end,
                candidate=candidate,
                pos=_normalize_pos(candidate.pos, allowed_pos),
            )
        )

    located.sort(key=lambda item: item.start)
    annotated_parts: list[str] = []
    items: list[AnnotationItem] = []
    cursor = 0
    for item in located:
        annotated_parts.append(source_text[cursor : item.start])
        annotated_parts.append(
            f"[[{item.candidate.source}|{item.candidate.translation}|{item.pos}]]"
        )
        items.append(
            AnnotationItem(
                word=item.candidate.source,
                translation=item.candidate.translation,
                context=_context_for(source_text, item.start, item.end),
                pos=item.pos,
            )
        )
        cursor = item.end
    annotated_parts.append(source_text[cursor:])

    return AnnotationProjection(
        annotated_text="".join(annotated_parts),
        items=items,
        rejections=rejections,
    )


def _candidate_shape_error(candidate: AnnotationCandidate) -> str | None:
    if not candidate.source.strip():
        return "empty_source"
    if not candidate.translation.strip():
        return "empty_translation"
    if any(char in candidate.source for char in _RESERVED_MARKER_CHARS):
        return "reserved_source_character"
    if any(char in candidate.translation for char in _RESERVED_MARKER_CHARS):
        return "reserved_translation_character"
    return None


def _source_positions(source_text: str, source: str) -> list[int]:
    positions: list[int] = []
    cursor = 0
    while True:
        start = source_text.find(source, cursor)
        if start < 0:
            return positions
        positions.append(start)
        cursor = start + 1


def _anchor_matching_positions(
    source_text: str,
    candidate: AnnotationCandidate,
    source_positions: list[int],
) -> list[int]:
    positions: list[int] = []
    for start in source_positions:
        end = start + len(candidate.source)
        prefix_matches = not candidate.prefix or source_text[:start].endswith(candidate.prefix)
        suffix_matches = not candidate.suffix or source_text[end:].startswith(candidate.suffix)
        if prefix_matches and suffix_matches:
            positions.append(start)
    return positions


def _normalize_pos(pos: str, allowed_pos: frozenset[str]) -> str:
    normalized = _POS_ALIASES.get(str(pos or "").strip().lower(), str(pos or "").strip().lower())
    if normalized in allowed_pos:
        return normalized
    return "other" if "other" in allowed_pos else sorted(allowed_pos)[0]


def _context_for(source_text: str, start: int, end: int) -> str:
    paragraph_start = source_text.rfind("\n\n", 0, start)
    paragraph_end = source_text.find("\n\n", end)
    left = paragraph_start + 2 if paragraph_start >= 0 else 0
    right = paragraph_end if paragraph_end >= 0 else len(source_text)
    return " ".join(source_text[left:right].split())[:240]
