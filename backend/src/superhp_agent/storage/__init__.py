"""SQLite storage implementations and their composition entrypoint.

Upper layers should depend on Store or Repository Ports. This package exposes
the AppDB entrypoint as a composition and lifecycle facade over the
separated connection, migration, and repository implementations.
"""

from superhp_agent.storage.app_db import AppDB

__all__ = [
    "AppDB",
]
