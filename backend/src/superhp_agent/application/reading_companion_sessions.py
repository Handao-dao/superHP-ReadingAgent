"""Coordinate durable HTTP sessions around the manual companion Runner.

The coordinator owns atomic start/resume/retry application operations. Raw
Episode state is checkpointed before the first model call and after every
bounded Agent run, so a backend restart does not erase the conversation.
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
    ReadingCompanionSession,
)
from superhp_agent.ports.repositories import ReadingCompanionRepository


class ReadingCompanionSessionNotFoundError(LookupError):
    """Raised when an HTTP caller references an unknown durable session."""


class ReadingCompanionSessionConflictError(RuntimeError):
    """Raised when a caller tries to replace an existing durable session."""


class ReadingCompanionSessionCoordinator:
    """Start, resume, retry, and restore manual reading conversations."""

    def __init__(
        self,
        runner: ManualReadingCompanionRunner,
        repository: ReadingCompanionRepository,
    ):
        self.runner = runner
        self.repository = repository
        # The current product is single-user. One lock makes state replacement
        # atomic inside this process without premature lock management.
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
            if self.repository.load_session(resolved_session_id) is not None:
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
            self.repository.create_session(
                ReadingCompanionSession(
                    session_id=resolved_session_id,
                    active_episode_id=state.episode.episode_id,
                )
            )
            # Preserve the user request even if the process stops during the
            # first provider call.
            self.repository.save_run_state(state)
            persisted_state = self.repository.load_active_run(
                resolved_session_id
            )
            if persisted_state is None:
                raise RuntimeError(
                    "failed to restore the newly persisted companion run"
                )
            state = persisted_state
            reply = await self.runner.run(state)
            self.repository.save_run_state(reply.state)
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
            self.repository.save_run_state(reply.state)
            return reply

    async def retry(self, session_id: str) -> ReadingCompanionReply:
        """Retry a recoverable pending model turn without adding a message."""
        async with self._lock:
            state = self._require_state(session_id)
            reply = await self.runner.run(state)
            self.repository.save_run_state(reply.state)
            return reply

    def load(self, session_id: str) -> ReadingCompanionRunState | None:
        """Restore immutable active state for a public read projection."""
        normalized = str(session_id or "").strip()
        if not normalized:
            return None
        return self.repository.load_active_run(normalized)

    def _require_state(self, session_id: str) -> ReadingCompanionRunState:
        normalized = str(session_id or "").strip()
        state = (
            self.repository.load_active_run(normalized)
            if normalized
            else None
        )
        if state is None:
            raise ReadingCompanionSessionNotFoundError(
                f"reading companion session not found: {normalized}"
            )
        return state
