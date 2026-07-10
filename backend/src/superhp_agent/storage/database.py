"""SQLite connection and concurrency boundary.

This object owns database-path creation, connection configuration, the shared
process lock, and connection shutdown. It does not define tables, run schema
migrations, or implement repository queries.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path


class SQLiteDatabase:
    """Own one configured SQLite connection shared by local repositories."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(
            self.path,
            check_same_thread=False,
            timeout=30,
        )
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        # FastAPI and WebSocket handlers can interleave on the same process.
        self.lock = threading.RLock()

    def close(self) -> None:
        self.connection.close()
