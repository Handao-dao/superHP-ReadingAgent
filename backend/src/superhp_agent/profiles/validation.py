"""Shared validation for the inline annotation format used by profiles.

Validation is deliberately deterministic: valid markers are restored to their
left-hand source text, then the restored passage must equal the original chunk.
"""

from __future__ import annotations

import re

from superhp_agent.contracts.annotation import ServiceIssue

ANNOTATION_MARKER_RE = re.compile(
    # Three non-empty fields; brackets and pipes are reserved delimiters.
    r"\[\[([^|\[\]]+)\|([^|\[\]]+)\|([^|\[\]]+)\]\]"
)


def validate_annotation_output(
    *,
    source_text: str,
    annotated_text: str,
    allowed_pos: frozenset[str],
) -> ServiceIssue | None:
    """Return the first validation issue, or ``None`` for safe model text.

    A valid result must use only complete three-field markers, use a label
    allowed by the active Profile, and reconstruct the source exactly after
    every marker is replaced by its left-hand field.
    """
    matches = list(ANNOTATION_MARKER_RE.finditer(annotated_text))
    restored = ANNOTATION_MARKER_RE.sub(lambda match: match.group(1), annotated_text)

    # A valid substitution removes every reserved delimiter. Anything left is
    # a partial marker or a legacy two-field marker and is unsafe for new data.
    if "[[" in restored or "]]" in restored:
        return ServiceIssue(
            category="validation",
            code="malformed_marker",
            message="The annotation marker format is incomplete or invalid.",
        )

    for match in matches:
        if match.group(3).strip() not in allowed_pos:
            return ServiceIssue(
                category="validation",
                code="invalid_pos",
                message="An annotation uses a label that is not allowed by the profile.",
            )

    # Only platform line endings are normalized. Whitespace and punctuation
    # remain strict so model rewrites cannot be hidden by a loose comparison.
    if _normalize_newlines(restored) != _normalize_newlines(source_text):
        return ServiceIssue(
            category="validation",
            code="source_mismatch",
            message="The model changed text outside the annotation markers.",
        )
    return None


def _normalize_newlines(text: str) -> str:
    """Treat Windows and Unix line endings as the same source text."""
    return text.replace("\r\n", "\n").replace("\r", "\n")
