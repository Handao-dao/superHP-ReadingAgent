"""Coordinate a manual reading Episode around the low-level companion Loop.

This application boundary freezes the opened unit, rebuilds trusted tool scope
for every turn, and supplies current Corpus metadata to the Agent. It does not
persist the transcript, expose HTTP, close Episodes, or generate memories.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from superhp_agent.agents.reading_companion import ReadingCompanionAgent
from superhp_agent.application.previous_reading_scope import (
    PreviousReadingScopeBuilder,
)
from superhp_agent.contracts import (
    AgentToolExecutionContext,
    ReadingCompanionEpisode,
    ReadingCompanionEpisodeTrigger,
    ReadingCompanionMessage,
    ReadingCompanionMessageRole,
    ReadingCompanionReply,
    ReadingCompanionRunState,
)
from superhp_agent.corpus import CorpusStore, ReadingUnit


class ManualReadingCompanionError(RuntimeError):
    """Stable application error for an invalid or stale reading invocation."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class ManualReadingCompanionRunner:
    """Start and advance one in-memory manual reading Episode."""

    def __init__(
        self,
        corpus: CorpusStore,
        scope_builder: PreviousReadingScopeBuilder,
        agent_factory: Callable[[], ReadingCompanionAgent],
    ):
        self.corpus = corpus
        self.scope_builder = scope_builder
        self.agent_factory = agent_factory

    def start(
        self,
        *,
        session_id: str,
        current_unit_id: str,
        user_message: str,
        selected_text: str = "",
        episode_id: str | None = None,
    ) -> ReadingCompanionRunState:
        """Freeze a manual invocation without calling the model."""
        session_id = str(session_id or "").strip()
        current_unit_id = str(current_unit_id or "").strip()
        if not session_id:
            raise ValueError("session_id is required")
        if not current_unit_id:
            raise ValueError("current_unit_id is required")
        if not isinstance(user_message, str) or not user_message.strip():
            raise ValueError("user_message is required")

        unit = self._find_unit(current_unit_id)
        resolved_episode_id = str(episode_id or uuid4().hex).strip()
        message = ReadingCompanionMessage(
            message_id=uuid4().hex,
            session_id=session_id,
            episode_id=resolved_episode_id,
            role=ReadingCompanionMessageRole.USER,
            content=user_message.strip(),
        )
        episode = ReadingCompanionEpisode(
            episode_id=resolved_episode_id,
            session_id=session_id,
            trigger=ReadingCompanionEpisodeTrigger.MANUAL_READING,
            start_message_id=message.message_id,
            book_id=unit.book_id,
            chapter_id=unit.chapter_id,
            unit_id=unit.id,
            selected_text=str(selected_text or "").strip(),
        )
        return ReadingCompanionRunState(
            episode=episode,
            conversation=(message,),
        )

    async def run(
        self,
        state: ReadingCompanionRunState,
        *,
        user_message: str | None = None,
        conversation_memory: str = "",
    ) -> ReadingCompanionReply:
        """Rebuild trusted scope, then advance the companion Loop."""
        episode = state.episode
        if episode.trigger is not ReadingCompanionEpisodeTrigger.MANUAL_READING:
            raise ManualReadingCompanionError(
                "invalid_episode",
                "Manual runner requires a manual_reading episode.",
            )
        unit = self._find_unit(episode.unit_id)
        if (
            unit.book_id != episode.book_id
            or unit.chapter_id != episode.chapter_id
        ):
            raise ManualReadingCompanionError(
                "scope_stale",
                "The frozen reading unit no longer matches its episode.",
            )
        try:
            scope = self.scope_builder.build(unit.id)
        except ValueError as exc:
            raise ManualReadingCompanionError(
                "scope_stale",
                "Unable to rebuild the trusted previous-reading scope.",
            ) from exc

        tool_context = AgentToolExecutionContext(
            session_id=episode.session_id,
            episode_id=episode.episode_id,
            language_id=unit.language_id,
            previous_reading_scope=scope,
        )
        return await self.agent_factory().run(
            state,
            tool_context=tool_context,
            book_title=unit.book_title,
            chapter_title=unit.chapter_title,
            chapter_no=unit.chapter_no,
            user_message=user_message,
            conversation_memory=conversation_memory,
        )

    def _find_unit(self, unit_id: str) -> ReadingUnit:
        unit = next(
            (
                candidate
                for candidate in self.corpus.list_units()
                if candidate.id == unit_id
            ),
            None,
        )
        if unit is None:
            raise ManualReadingCompanionError(
                "no_active_reading",
                f"Unknown reading unit id: {unit_id}",
            )
        return unit
