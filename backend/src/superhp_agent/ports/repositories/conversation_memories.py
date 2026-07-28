"""Persistence capability for append-only compressed conversation memory.

Memory is deliberately separate from raw companion messages. A failed or
superseded summary remains auditable and never replaces the source transcript.
"""

from typing import Protocol, runtime_checkable

from superhp_agent.contracts import ConversationMemory, ConversationMemoryKind


@runtime_checkable
class ConversationMemoryRepository(Protocol):
    """Append and query versioned memories for one long-lived Session."""

    def save(self, memory: ConversationMemory) -> None: ...

    def list_for_session(
        self,
        session_id: str,
        *,
        kind: ConversationMemoryKind | None = None,
    ) -> tuple[ConversationMemory, ...]: ...

    def next_revision(
        self,
        session_id: str,
        kind: ConversationMemoryKind,
    ) -> int: ...
