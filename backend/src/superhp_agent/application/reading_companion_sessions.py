"""Coordinate durable HTTP sessions around the manual companion Runner.

The coordinator owns atomic start/resume/retry application operations. Raw
Episode state is checkpointed before the first model call and after every
bounded Agent run, so a backend restart does not erase the conversation.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime
from uuid import uuid4

from superhp_agent.application.manual_reading_companion import (
    ManualReadingCompanionRunner,
)
from superhp_agent.contracts import (
    ConversationMemory,
    ConversationMemoryKind,
    ConversationMemoryStatus,
    ReadingCompanionEpisodeEndReason,
    ReadingCompanionEpisodeState,
    ReadingCompanionReply,
    ReadingCompanionRunState,
    ReadingCompanionSession,
)
from superhp_agent.ports.repositories import ReadingCompanionRepository
from superhp_agent.services.conversation_memory import (
    ConversationCompactionPolicy,
    ConversationMemoryGenerator,
)


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
        memory_generator: ConversationMemoryGenerator,
        compaction_policy: ConversationCompactionPolicy | None = None,
    ):
        self.runner = runner
        self.repository = repository
        self.memory_generator = memory_generator
        self.compaction_policy = (
            compaction_policy or ConversationCompactionPolicy()
        )
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
            existing_session = self.repository.load_session(
                resolved_session_id
            )
            if (
                existing_session is not None
                and existing_session.active_episode_id
            ):
                raise ReadingCompanionSessionConflictError(
                    "reading companion session already has an active episode: "
                    f"{resolved_session_id}"
                )
            state = self.runner.start(
                session_id=resolved_session_id,
                current_unit_id=current_unit_id,
                user_message=user_message,
                selected_text=selected_text,
            )
            if existing_session is None:
                self.repository.create_session(
                    ReadingCompanionSession(
                        session_id=resolved_session_id,
                        active_episode_id=state.episode.episode_id,
                    )
                )
            return await self._run_and_checkpoint(state)

    async def resume(
        self,
        session_id: str,
        *,
        user_message: str,
    ) -> ReadingCompanionReply:
        """Append one user message and run the next bounded Agent turn."""
        async with self._lock:
            state = self._require_state(session_id)
            state = self.runner.continue_with_user_message(
                state,
                user_message,
            )
            return await self._run_and_checkpoint(state)

    async def retry(self, session_id: str) -> ReadingCompanionReply:
        """Retry a recoverable pending model turn without adding a message."""
        async with self._lock:
            state = self._require_state(session_id)
            return await self._run_and_checkpoint(state)

    async def end(
        self,
        session_id: str,
        *,
        reason: ReadingCompanionEpisodeEndReason = (
            ReadingCompanionEpisodeEndReason.USER_ENDED
        ),
    ) -> ConversationMemory:
        """Close one Episode and idempotently finish its passive summary."""
        async with self._lock:
            session = self.load_session(session_id)
            if session is None:
                raise ReadingCompanionSessionNotFoundError(
                    f"reading companion session not found: {session_id}"
                )
            state = (
                self.repository.load_active_run(session.session_id)
                if session.active_episode_id
                else self.repository.load_latest_run(session.session_id)
            )
            if state is None:
                raise ReadingCompanionSessionNotFoundError(
                    "reading companion session has no episode: "
                    f"{session.session_id}"
                )
            memory = self.memory_generator.latest_for_episode(
                session.session_id,
                state.episode.episode_id,
                kind=ConversationMemoryKind.EPISODE_SUMMARY,
            )
            if memory is None:
                # Pending is durable before the Episode pointer is cleared.
                # A retry can therefore resume either side of a process exit.
                memory = self.memory_generator.prepare(
                    state,
                    kind=ConversationMemoryKind.EPISODE_SUMMARY,
                )
            if session.active_episode_id:
                final_state = (
                    ReadingCompanionEpisodeState.ABANDONED
                    if reason
                    in {
                        ReadingCompanionEpisodeEndReason.USER_ABANDONED,
                        ReadingCompanionEpisodeEndReason.UNRECOVERABLE_ERROR,
                    }
                    else ReadingCompanionEpisodeState.COMPLETED
                )
                episode = replace(
                    state.episode,
                    state=final_state,
                    end_message_id=state.conversation[-1].message_id,
                    end_reason=reason,
                    ended_at=datetime.now().astimezone().isoformat(
                        timespec="seconds"
                    ),
                )
                self.repository.close_active_episode(episode)
            if memory.status is not ConversationMemoryStatus.PENDING:
                return memory
            return await self.memory_generator.finish(state, memory)

    def load(self, session_id: str) -> ReadingCompanionRunState | None:
        """Restore immutable active state for a public read projection."""
        normalized = str(session_id or "").strip()
        if not normalized:
            return None
        return self.repository.load_active_run(normalized)

    def load_session(
        self,
        session_id: str,
    ) -> ReadingCompanionSession | None:
        """Restore the long-lived Session even when no Episode is active."""
        normalized = str(session_id or "").strip()
        if not normalized:
            return None
        return self.repository.load_session(normalized)

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

    async def _compact_reply(
        self,
        reply: ReadingCompanionReply,
    ) -> ReadingCompanionReply:
        compacted = await self.memory_generator.compact_if_needed(
            reply.state,
            policy=self.compaction_policy,
        )
        if compacted == reply.state:
            return reply
        self.repository.save_run_state(compacted)
        return replace(reply, state=compacted)

    async def _run_and_checkpoint(
        self,
        state: ReadingCompanionRunState,
    ) -> ReadingCompanionReply:
        """Persist the pending user turn before entering the model Loop."""
        self.repository.save_run_state(state)
        persisted = self.repository.load_active_run(
            state.episode.session_id
        )
        if persisted is None:
            raise RuntimeError(
                "failed to restore the persisted companion turn"
            )
        reply = await self.runner.run(
            persisted,
            conversation_memory=(
                self.memory_generator.context_for_session(
                    persisted.episode.session_id,
                    episode_id=persisted.episode.episode_id,
                )
            ),
        )
        self.repository.save_run_state(reply.state)
        return await self._compact_reply(reply)
