"""SQLite persistence for resumable recommendation Agent sessions.

The adapter stores one complete session aggregate as versioned JSON while also
keeping its current phase in a queryable column. Explicit decoding reconstructs
the stable Contracts instead of leaking database dictionaries into the Agent.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from superhp_agent.contracts import (
    BookDifficulty,
    BookRecommendationHandoff,
    BookSnapshot,
    LLMToolCall,
    OperationalReadingBand,
    ReadingDifficultyEvidence,
    ReadingPreference,
    RecommendationAgentMessage,
    RecommendationAgentMessageRole,
    RecommendationAgentPhase,
    RecommendationAgentSession,
    RecommendationOrigin,
    RecommendationRequest,
)
from superhp_agent.storage.database import SQLiteDatabase

_SESSION_SCHEMA_VERSION = 1


class SQLiteRecommendationSessionRepository:
    """Persist complete recommendation transcripts on the shared connection."""

    def __init__(self, database: SQLiteDatabase):
        self.database = database

    def save(self, session: RecommendationAgentSession) -> None:
        """Insert or replace the latest state without changing its creation time."""
        payload = json.dumps(
            {
                "schema_version": _SESSION_SCHEMA_VERSION,
                "session": asdict(session),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        with self.database.lock:
            self.database.connection.execute(
                """
                INSERT INTO recommendation_sessions (
                    session_id,
                    phase,
                    session_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, datetime('now','localtime'), datetime('now','localtime'))
                ON CONFLICT(session_id) DO UPDATE SET
                    phase=excluded.phase,
                    session_json=excluded.session_json,
                    updated_at=excluded.updated_at
                """,
                (session.session_id, session.phase.value, payload),
            )
            self.database.connection.commit()

    def load(self, session_id: str) -> RecommendationAgentSession | None:
        """Return the latest complete session, or ``None`` when it does not exist."""
        session_id = _require_session_id(session_id)
        with self.database.lock:
            row = self.database.connection.execute(
                """
                SELECT phase, session_json
                FROM recommendation_sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(str(row["session_json"]))
            if payload.get("schema_version") != _SESSION_SCHEMA_VERSION:
                raise ValueError("unsupported recommendation session schema")
            session = _session_from_dict(payload["session"])
        except (
            AttributeError,
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            raise ValueError(
                f"invalid stored recommendation session: {session_id}"
            ) from exc
        if session.session_id != session_id:
            raise ValueError(
                f"stored recommendation session id mismatch: {session_id}"
            )
        if session.phase.value != str(row["phase"]):
            raise ValueError(
                f"stored recommendation session phase mismatch: {session_id}"
            )
        return session

    def delete(self, session_id: str) -> bool:
        """Remove one conversation and report whether a row existed."""
        session_id = _require_session_id(session_id)
        with self.database.lock:
            cursor = self.database.connection.execute(
                "DELETE FROM recommendation_sessions WHERE session_id = ?",
                (session_id,),
            )
            self.database.connection.commit()
        return cursor.rowcount > 0


def _session_from_dict(data: dict[str, Any]) -> RecommendationAgentSession:
    return RecommendationAgentSession(
        session_id=str(data["session_id"]),
        request=_request_from_dict(data["request"]),
        phase=RecommendationAgentPhase(str(data["phase"])),
        conversation=tuple(
            _message_from_dict(message)
            for message in data.get("conversation", ())
        ),
        tool_call_count=int(data.get("tool_call_count", 0)),
        observed_catalog_ids=_string_tuple(data.get("observed_catalog_ids", ())),
        recommended_catalog_ids=_string_tuple(
            data.get("recommended_catalog_ids", ())
        ),
        error_code=str(data.get("error_code", "")),
    )


def _request_from_dict(data: dict[str, Any]) -> RecommendationRequest:
    operational_band = data.get("operational_band")
    handoff = data.get("handoff")
    return RecommendationRequest(
        origin=RecommendationOrigin(str(data["origin"])),
        preferred_genres=_string_tuple(data.get("preferred_genres", ())),
        excluded_traits=_string_tuple(data.get("excluded_traits", ())),
        reading_preference=ReadingPreference(
            str(data.get("reading_preference", ReadingPreference.BALANCED))
        ),
        operational_band=(
            _band_from_dict(operational_band)
            if operational_band is not None
            else None
        ),
        reference_books=tuple(
            _book_from_dict(book) for book in data.get("reference_books", ())
        ),
        handoff=_handoff_from_dict(handoff) if handoff is not None else None,
        user_notes=str(data.get("user_notes", "")),
    )


def _message_from_dict(data: dict[str, Any]) -> RecommendationAgentMessage:
    return RecommendationAgentMessage(
        role=RecommendationAgentMessageRole(str(data["role"])),
        content=str(data.get("content", "")),
        tool_calls=tuple(
            _tool_call_from_dict(tool_call)
            for tool_call in data.get("tool_calls", ())
        ),
        tool_call_id=str(data.get("tool_call_id", "")),
        tool_name=str(data.get("tool_name", "")),
        is_error=bool(data.get("is_error", False)),
    )


def _tool_call_from_dict(data: dict[str, Any]) -> LLMToolCall:
    arguments = data.get("arguments", {})
    if not isinstance(arguments, dict):
        raise ValueError("stored tool arguments must be an object")
    return LLMToolCall(
        id=str(data["id"]),
        name=str(data["name"]),
        arguments=arguments,
        raw_arguments=str(data.get("raw_arguments", "")),
        arguments_error=str(data.get("arguments_error", "")),
    )


def _handoff_from_dict(data: dict[str, Any]) -> BookRecommendationHandoff:
    target_band = data.get("target_band")
    return BookRecommendationHandoff(
        current_book=_book_from_dict(data["current_book"]),
        evidence=_evidence_from_dict(data["evidence"]),
        target_band=(
            _band_from_dict(target_band) if target_band is not None else None
        ),
        preserve_genre_by_default=bool(
            data.get("preserve_genre_by_default", True)
        ),
    )


def _book_from_dict(data: dict[str, Any]) -> BookSnapshot:
    difficulty = data.get("difficulty")
    progress = data.get("progress")
    return BookSnapshot(
        book_id=str(data["book_id"]),
        title=str(data["title"]),
        title_zh=str(data.get("title_zh", "")),
        author=str(data.get("author", "")),
        difficulty=(
            _difficulty_from_dict(difficulty)
            if difficulty is not None
            else None
        ),
        genres=_string_tuple(data.get("genres", ())),
        progress=float(progress) if progress is not None else None,
    )


def _difficulty_from_dict(data: dict[str, Any]) -> BookDifficulty:
    return BookDifficulty(
        minimum_lexile=int(data["minimum_lexile"]),
        maximum_lexile=int(data["maximum_lexile"]),
    )


def _band_from_dict(data: dict[str, Any]) -> OperationalReadingBand:
    return OperationalReadingBand(
        minimum_lexile=int(data["minimum_lexile"]),
        maximum_lexile=int(data["maximum_lexile"]),
        confidence=float(data.get("confidence", 0.0)),
        evidence_source=str(data.get("evidence_source", "")),
    )


def _evidence_from_dict(data: dict[str, Any]) -> ReadingDifficultyEvidence:
    annotation_target = data.get("annotation_target")
    return ReadingDifficultyEvidence(
        observed_word_count=int(data["observed_word_count"]),
        observed_chapter_count=int(data["observed_chapter_count"]),
        lookup_density=float(data["lookup_density"]),
        unique_lookup_density=float(data.get("unique_lookup_density", 0.0)),
        repeated_lookup_density=float(data.get("repeated_lookup_density", 0.0)),
        annotated_lookup_density=float(
            data.get("annotated_lookup_density", 0.0)
        ),
        actual_annotation_density=float(
            data.get("actual_annotation_density", 0.0)
        ),
        annotation_target=(
            int(annotation_target) if annotation_target is not None else None
        ),
    )


def _string_tuple(values: object) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        raise ValueError("stored string collection must be an array")
    return tuple(str(value) for value in values)


def _require_session_id(session_id: str) -> str:
    value = str(session_id or "").strip()
    if not value:
        raise ValueError("session_id is required")
    return value
