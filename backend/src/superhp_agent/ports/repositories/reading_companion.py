"""Persistence capabilities for long-lived reading companion conversations.

The Port treats Session, Episode, and raw Message records as one durable
conversation aggregate. It does not decide when an Episode ends, call a model,
or generate compressed memory.
"""

from typing import Protocol, runtime_checkable

from superhp_agent.contracts import (
    ReadingCompanionEpisode,
    ReadingCompanionRunState,
    ReadingCompanionSession,
    ReadingCompanionTranscript,
)


@runtime_checkable
class ReadingCompanionRepository(Protocol):
    """Persist and restore companion identity plus its active Episode."""

    def create_session(self, session: ReadingCompanionSession) -> None: ...

    def load_session(
        self,
        session_id: str,
    ) -> ReadingCompanionSession | None: ...

    def save_run_state(self, state: ReadingCompanionRunState) -> None: ...

    def load_active_run(
        self,
        session_id: str,
    ) -> ReadingCompanionRunState | None: ...

    def load_latest_run(
        self,
        session_id: str,
    ) -> ReadingCompanionTranscript | None: ...

    def close_active_episode(
        self,
        episode: ReadingCompanionEpisode,
    ) -> None: ...
