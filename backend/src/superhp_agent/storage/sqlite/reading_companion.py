"""SQLite persistence for companion Sessions, Episodes, and raw Messages.

Messages are inserted once and verified on repeated aggregate saves. This
preserves the exact model/tool transcript as the durable source of truth while
allowing the active Episode snapshot to advance transactionally.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict

from superhp_agent.contracts import (
    LLMToolCall,
    ReadingCompanionEpisode,
    ReadingCompanionEpisodeEndReason,
    ReadingCompanionEpisodeState,
    ReadingCompanionEpisodeTrigger,
    ReadingCompanionMessage,
    ReadingCompanionMessageRole,
    ReadingCompanionRunState,
    ReadingCompanionSession,
    ReadingCompanionSessionStatus,
)
from superhp_agent.storage.database import SQLiteDatabase


class SQLiteReadingCompanionRepository:
    """Store the active companion aggregate on the shared SQLite connection."""

    def __init__(self, database: SQLiteDatabase):
        self.database = database

    def create_session(self, session: ReadingCompanionSession) -> None:
        """Create a long-lived identity without silently replacing one."""
        with self.database.lock, self.database.connection:
            self.database.connection.execute(
                """
                INSERT INTO reading_companion_sessions (
                    session_id,
                    reader_key,
                    status,
                    active_episode_id,
                    created_at,
                    updated_at
                )
                VALUES (
                    ?, ?, ?, ?, 
                    COALESCE(NULLIF(?, ''), datetime('now','localtime')),
                    COALESCE(NULLIF(?, ''), datetime('now','localtime'))
                )
                """,
                (
                    session.session_id,
                    session.reader_key,
                    session.status.value,
                    session.active_episode_id,
                    session.created_at,
                    session.updated_at,
                ),
            )

    def load_session(
        self,
        session_id: str,
    ) -> ReadingCompanionSession | None:
        """Restore one Session identity and its active Episode pointer."""
        session_id = _require_id(session_id, "session_id")
        with self.database.lock:
            row = self.database.connection.execute(
                """
                SELECT
                    session_id,
                    reader_key,
                    status,
                    active_episode_id,
                    created_at,
                    updated_at
                FROM reading_companion_sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        return _session_from_row(row) if row is not None else None

    def save_run_state(self, state: ReadingCompanionRunState) -> None:
        """Advance one active Episode while keeping old messages immutable."""
        episode = state.episode
        with self.database.lock, self.database.connection:
            session_row = self.database.connection.execute(
                """
                SELECT status, active_episode_id
                FROM reading_companion_sessions
                WHERE session_id = ?
                """,
                (episode.session_id,),
            ).fetchone()
            if session_row is None:
                raise ValueError(
                    "companion session must exist before saving a run"
                )
            if str(session_row["status"]) != (
                ReadingCompanionSessionStatus.ACTIVE.value
            ):
                raise ValueError("cannot save a run for an archived session")
            active_episode_id = str(session_row["active_episode_id"])
            if active_episode_id and active_episode_id != episode.episode_id:
                raise ValueError(
                    "session already points to another active episode"
                )

            self._upsert_episode(state)
            self._append_messages(state)
            self.database.connection.execute(
                """
                UPDATE reading_companion_sessions
                SET
                    active_episode_id = ?,
                    updated_at = datetime('now','localtime')
                WHERE session_id = ?
                """,
                (episode.episode_id, episode.session_id),
            )

    def load_active_run(
        self,
        session_id: str,
    ) -> ReadingCompanionRunState | None:
        """Restore the complete active Episode transcript after a restart."""
        session = self.load_session(session_id)
        if session is None or not session.active_episode_id:
            return None
        with self.database.lock:
            episode_row = self.database.connection.execute(
                """
                SELECT *
                FROM reading_companion_episodes
                WHERE episode_id = ? AND session_id = ?
                """,
                (session.active_episode_id, session.session_id),
            ).fetchone()
            message_rows = self.database.connection.execute(
                """
                SELECT *
                FROM reading_companion_messages
                WHERE episode_id = ?
                ORDER BY sequence_no ASC
                """,
                (session.active_episode_id,),
            ).fetchall()
        if episode_row is None:
            raise ValueError(
                "companion session points to a missing active episode"
            )
        episode = _episode_from_row(episode_row)
        if episode.state is not ReadingCompanionEpisodeState.ACTIVE:
            raise ValueError(
                "companion session points to a non-active episode"
            )
        return ReadingCompanionRunState(
            episode=episode,
            conversation=tuple(
                _message_from_row(row) for row in message_rows
            ),
            tool_call_count=int(episode_row["tool_call_count"]),
            error_code=str(episode_row["error_code"]),
        )

    def _upsert_episode(self, state: ReadingCompanionRunState) -> None:
        episode = state.episode
        self.database.connection.execute(
            """
            INSERT INTO reading_companion_episodes (
                episode_id,
                session_id,
                trigger,
                start_message_id,
                state,
                book_id,
                chapter_id,
                unit_id,
                selected_text,
                end_message_id,
                end_reason,
                tool_call_count,
                error_code,
                created_at,
                ended_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                COALESCE(NULLIF(?, ''), datetime('now','localtime')),
                ?
            )
            ON CONFLICT(episode_id) DO UPDATE SET
                state=excluded.state,
                end_message_id=excluded.end_message_id,
                end_reason=excluded.end_reason,
                tool_call_count=excluded.tool_call_count,
                error_code=excluded.error_code,
                ended_at=excluded.ended_at
            """,
            (
                episode.episode_id,
                episode.session_id,
                episode.trigger.value,
                episode.start_message_id,
                episode.state.value,
                episode.book_id,
                episode.chapter_id,
                episode.unit_id,
                episode.selected_text,
                episode.end_message_id,
                episode.end_reason.value if episode.end_reason else None,
                state.tool_call_count,
                state.error_code,
                episode.created_at,
                episode.ended_at,
            ),
        )
        row = self.database.connection.execute(
            """
            SELECT
                session_id,
                trigger,
                start_message_id,
                book_id,
                chapter_id,
                unit_id,
                selected_text
            FROM reading_companion_episodes
            WHERE episode_id = ?
            """,
            (episode.episode_id,),
        ).fetchone()
        expected = (
            episode.session_id,
            episode.trigger.value,
            episode.start_message_id,
            episode.book_id,
            episode.chapter_id,
            episode.unit_id,
            episode.selected_text,
        )
        actual = tuple(str(row[key]) for key in row.keys())
        if actual != expected:
            raise ValueError("stored companion episode identity is immutable")

    def _append_messages(self, state: ReadingCompanionRunState) -> None:
        for sequence_no, message in enumerate(state.conversation):
            encoded_tool_calls = _encode_tool_calls(message.tool_calls)
            existing = self.database.connection.execute(
                """
                SELECT
                    session_id,
                    episode_id,
                    sequence_no,
                    role,
                    content,
                    tool_calls_json,
                    tool_call_id,
                    tool_name,
                    is_error
                FROM reading_companion_messages
                WHERE message_id = ?
                """,
                (message.message_id,),
            ).fetchone()
            values = (
                message.session_id,
                message.episode_id,
                sequence_no,
                message.role.value,
                message.content,
                encoded_tool_calls,
                message.tool_call_id,
                message.tool_name,
                int(message.is_error),
            )
            if existing is not None:
                actual = tuple(existing[key] for key in existing.keys())
                if actual != values:
                    raise ValueError(
                        "stored companion message cannot be rewritten"
                    )
                continue
            self.database.connection.execute(
                """
                INSERT INTO reading_companion_messages (
                    message_id,
                    session_id,
                    episode_id,
                    sequence_no,
                    role,
                    content,
                    tool_calls_json,
                    tool_call_id,
                    tool_name,
                    is_error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (message.message_id, *values),
            )


def _session_from_row(row: sqlite3.Row) -> ReadingCompanionSession:
    return ReadingCompanionSession(
        session_id=str(row["session_id"]),
        reader_key=str(row["reader_key"]),
        status=ReadingCompanionSessionStatus(str(row["status"])),
        active_episode_id=str(row["active_episode_id"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _episode_from_row(row: sqlite3.Row) -> ReadingCompanionEpisode:
    end_reason = row["end_reason"]
    return ReadingCompanionEpisode(
        episode_id=str(row["episode_id"]),
        session_id=str(row["session_id"]),
        trigger=ReadingCompanionEpisodeTrigger(str(row["trigger"])),
        start_message_id=str(row["start_message_id"]),
        state=ReadingCompanionEpisodeState(str(row["state"])),
        book_id=str(row["book_id"]),
        chapter_id=str(row["chapter_id"]),
        unit_id=str(row["unit_id"]),
        selected_text=str(row["selected_text"]),
        end_message_id=str(row["end_message_id"]),
        end_reason=(
            ReadingCompanionEpisodeEndReason(str(end_reason))
            if end_reason is not None
            else None
        ),
        created_at=str(row["created_at"]),
        ended_at=str(row["ended_at"]),
    )


def _message_from_row(row: sqlite3.Row) -> ReadingCompanionMessage:
    try:
        raw_tool_calls = json.loads(str(row["tool_calls_json"]))
        tool_calls = tuple(
            _tool_call_from_dict(item) for item in raw_tool_calls
        )
    except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"invalid stored tool calls for message: {row['message_id']}"
        ) from exc
    return ReadingCompanionMessage(
        message_id=str(row["message_id"]),
        session_id=str(row["session_id"]),
        episode_id=str(row["episode_id"]),
        role=ReadingCompanionMessageRole(str(row["role"])),
        content=str(row["content"]),
        tool_calls=tool_calls,
        tool_call_id=str(row["tool_call_id"]),
        tool_name=str(row["tool_name"]),
        is_error=bool(row["is_error"]),
    )


def _encode_tool_calls(tool_calls: tuple[LLMToolCall, ...]) -> str:
    return json.dumps(
        [asdict(tool_call) for tool_call in tool_calls],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _tool_call_from_dict(data: object) -> LLMToolCall:
    if not isinstance(data, dict):
        raise ValueError("stored tool call must be an object")
    arguments = data.get("arguments", {})
    if not isinstance(arguments, dict):
        raise ValueError("stored tool call arguments must be an object")
    return LLMToolCall(
        id=str(data["id"]),
        name=str(data["name"]),
        arguments=arguments,
        raw_arguments=str(data.get("raw_arguments", "")),
        arguments_error=str(data.get("arguments_error", "")),
    )


def _require_id(value: str, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized

