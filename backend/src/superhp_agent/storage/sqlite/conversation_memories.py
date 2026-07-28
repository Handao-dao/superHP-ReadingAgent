"""SQLite persistence for versioned companion conversation memories.

A memory row may move once from ``pending`` to ``ready`` or ``failed``.
Completed rows and prior revisions are immutable, so raw history and summary
provenance remain inspectable when compression behavior evolves.
"""

from __future__ import annotations

import sqlite3

from superhp_agent.contracts import (
    ConversationMemory,
    ConversationMemoryKind,
    ConversationMemoryStatus,
)
from superhp_agent.storage.database import SQLiteDatabase


class SQLiteConversationMemoryRepository:
    """Store append-only summary revisions on the shared connection."""

    def __init__(self, database: SQLiteDatabase):
        self.database = database

    def save(self, memory: ConversationMemory) -> None:
        """Create a revision or finish its pending generation lifecycle."""
        with self.database.lock, self.database.connection:
            existing = self.database.connection.execute(
                """
                SELECT *
                FROM conversation_memories
                WHERE memory_id = ?
                """,
                (memory.memory_id,),
            ).fetchone()
            if existing is None:
                self._insert(memory)
                return
            stored = _memory_from_row(existing)
            if stored == memory:
                return
            if stored.status is not ConversationMemoryStatus.PENDING:
                raise ValueError("completed conversation memory is immutable")
            if (
                stored.session_id != memory.session_id
                or stored.episode_id != memory.episode_id
                or stored.kind is not memory.kind
                or stored.revision != memory.revision
                or stored.source_start_message_id
                != memory.source_start_message_id
                or stored.source_end_message_id
                != memory.source_end_message_id
                or (
                    memory.created_at
                    and stored.created_at != memory.created_at
                )
            ):
                raise ValueError("conversation memory provenance is immutable")
            if memory.status is ConversationMemoryStatus.PENDING:
                raise ValueError("pending conversation memory did not advance")
            self.database.connection.execute(
                """
                UPDATE conversation_memories
                SET
                    status = ?,
                    summary = ?,
                    error_code = ?,
                    input_tokens = ?,
                    output_tokens = ?
                WHERE memory_id = ?
                """,
                (
                    memory.status.value,
                    memory.summary,
                    memory.error_code,
                    memory.input_tokens,
                    memory.output_tokens,
                    memory.memory_id,
                ),
            )

    def list_for_session(
        self,
        session_id: str,
        *,
        kind: ConversationMemoryKind | None = None,
    ) -> tuple[ConversationMemory, ...]:
        """Return revisions in creation order, optionally for one kind."""
        session_id = _require_session_id(session_id)
        query = """
            SELECT *
            FROM conversation_memories
            WHERE session_id = ?
        """
        params: tuple[object, ...] = (session_id,)
        if kind is not None:
            query += " AND kind = ?"
            params += (kind.value,)
        query += " ORDER BY created_at ASC, revision ASC"
        with self.database.lock:
            rows = self.database.connection.execute(query, params).fetchall()
        return tuple(_memory_from_row(row) for row in rows)

    def next_revision(
        self,
        session_id: str,
        kind: ConversationMemoryKind,
    ) -> int:
        """Reserve no state; report the next revision under the caller lock."""
        session_id = _require_session_id(session_id)
        with self.database.lock:
            row = self.database.connection.execute(
                """
                SELECT COALESCE(MAX(revision), 0) AS latest_revision
                FROM conversation_memories
                WHERE session_id = ? AND kind = ?
                """,
                (session_id, kind.value),
            ).fetchone()
        return int(row["latest_revision"]) + 1

    def _insert(self, memory: ConversationMemory) -> None:
        self.database.connection.execute(
            """
            INSERT INTO conversation_memories (
                memory_id,
                session_id,
                episode_id,
                kind,
                revision,
                source_start_message_id,
                source_end_message_id,
                status,
                summary,
                error_code,
                input_tokens,
                output_tokens,
                created_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 
                COALESCE(NULLIF(?, ''), datetime('now','localtime'))
            )
            """,
            (
                memory.memory_id,
                memory.session_id,
                memory.episode_id,
                memory.kind.value,
                memory.revision,
                memory.source_start_message_id,
                memory.source_end_message_id,
                memory.status.value,
                memory.summary,
                memory.error_code,
                memory.input_tokens,
                memory.output_tokens,
                memory.created_at,
            ),
        )


def _memory_from_row(row: sqlite3.Row) -> ConversationMemory:
    return ConversationMemory(
        memory_id=str(row["memory_id"]),
        session_id=str(row["session_id"]),
        episode_id=str(row["episode_id"]),
        kind=ConversationMemoryKind(str(row["kind"])),
        revision=int(row["revision"]),
        source_start_message_id=str(row["source_start_message_id"]),
        source_end_message_id=str(row["source_end_message_id"]),
        status=ConversationMemoryStatus(str(row["status"])),
        summary=str(row["summary"]),
        error_code=str(row["error_code"]),
        input_tokens=int(row["input_tokens"]),
        output_tokens=int(row["output_tokens"]),
        created_at=str(row["created_at"]),
    )


def _require_session_id(session_id: str) -> str:
    normalized = str(session_id or "").strip()
    if not normalized:
        raise ValueError("session_id is required")
    return normalized
