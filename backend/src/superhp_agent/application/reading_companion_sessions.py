"""Coordinate temporary HTTP sessions around the manual companion Runner.

This is deliberately an in-memory transition boundary. It keeps FastAPI from
owning Agent state while the long-lived Session/Message repository is still
being designed. Restarting the backend clears every state stored here.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from superhp_agent.application.manual_reading_companion import (
    ManualReadingCompanionRunner,
)
from superhp_agent.contracts import (
    ReadingCompanionReply,
    ReadingCompanionRunState,
)


class ReadingCompanionSessionNotFoundError(LookupError):
    """Raised when an HTTP caller references an unknown in-memory session."""


class ReadingCompanionSessionConflictError(RuntimeError):
    """Raised when a caller tries to replace an active in-memory session."""


class InMemoryReadingCompanionSessionCoordinator:
    """Start, resume, retry, and inspect manual reading conversations."""

    def __init__(self, runner: ManualReadingCompanionRunner):
        self.runner = runner
        self._states: dict[str, ReadingCompanionRunState] = {}
        # The current product is single-user. One lock makes state replacement
        # atomic without introducing premature per-session lock management.
        self._lock = asyncio.Lock()

    async def start(
        self,
        *,
        current_unit_id: str,
        user_message: str,
        selected_text: str = "",
        session_id: str | None = None,
    ) -> ReadingCompanionReply:
        """Create one manual Episode and run its first model turn."""
        resolved_session_id = str(session_id or uuid4().hex).strip()
        if not resolved_session_id:
            raise ValueError("session_id must not be empty")

        async with self._lock:
            if resolved_session_id in self._states:
                raise ReadingCompanionSessionConflictError(
                    "reading companion session already exists: "
                    f"{resolved_session_id}"
                )
            state = self.runner.start(
                session_id=resolved_session_id,
                current_unit_id=current_unit_id,
                user_message=user_message,
                selected_text=selected_text,
            )
            reply = await self.runner.run(state)
            self._states[resolved_session_id] = reply.state
            return reply

    async def resume(
        self,
        session_id: str,
        *,
        user_message: str,
    ) -> ReadingCompanionReply:
        """Append one user message and run the next bounded Agent turn."""
        async with self._lock:
            state = self._require_state(session_id)
            reply = await self.runner.run(
                state,
                user_message=user_message,
            )
            self._states[state.episode.session_id] = reply.state
            return reply

    async def retry(self, session_id: str) -> ReadingCompanionReply:
        """Retry a recoverable pending model turn without adding a message."""
        async with self._lock:
            state = self._require_state(session_id)
            reply = await self.runner.run(state)
            self._states[state.episode.session_id] = reply.state
            return reply

    def load(self, session_id: str) -> ReadingCompanionRunState | None:
        """Return immutable in-memory state for a public read projection."""
        return self._states.get(str(session_id or "").strip())

    def _require_state(self, session_id: str) -> ReadingCompanionRunState:
        normalized = str(session_id or "").strip()
        state = self._states.get(normalized)
        if state is None:
            raise ReadingCompanionSessionNotFoundError(
                f"reading companion session not found: {normalized}"
            )
        return state
