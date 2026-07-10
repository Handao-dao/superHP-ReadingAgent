"""SQLite storage implementations and compatibility exports.

Upper layers should depend on Store or Repository Ports. This package exposes
the historical AppDB entrypoint while its connection, migration, and repository
responsibilities are separated incrementally.
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
