"""SQLite storage implementations and compatibility exports.

Upper layers should depend on Store or Repository Ports. This package exposes
the historical AppDB entrypoint as a composition and lifecycle facade over the
separated connection, migration, and repository implementations.
"""

from superhp_agent.storage.app_db import (
    ANNOTATION_MARKER_RE,
    VALID_BODY_KINDS,
    AppDB,
    normalize_pos,
    strip_annotation_markers,
)

__all__ = [
    "ANNOTATION_MARKER_RE",
    "VALID_BODY_KINDS",
    "AppDB",
    "normalize_pos",
    "strip_annotation_markers",
]
