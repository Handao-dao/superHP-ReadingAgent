"""Low-level observe-model-tool loop for manual reading conversations.

The Loop owns native transcript progression and tool repetition. It does not
load Corpus state, build spoiler scope, persist messages, end Episodes, or
perform recommendation-specific candidate transitions.
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from uuid import uuid4

from superhp_agent.agent_tools.registry import (
    AgentToolNotAllowedError,
    ToolRegistry,
    UnknownAgentToolError,
)
from superhp_agent.agents.companion_context import (
    ReadingCompanionContextBuilder,
)
from superhp_agent.contracts import (
    AgentToolExecutionContext,
    LLMToolCall,
    ReadingCompanionMessage,
    ReadingCompanionMessageRole,
    ReadingCompanionObservation,
    ReadingCompanionReply,
    ReadingCompanionRunState,
)
from superhp_agent.ports import LLMProvider

logger = logging.getLogger(__name__)


class ReadingCompanionStateError(RuntimeError):
    """Raised when a caller resumes a companion turn incorrectly."""


class ReadingCompanionAgent:
    """Advance an active reading Episode until user-visible text is ready."""

    def __init__(
        self,
        provider: LLMProvider,
        context_builder: ReadingCompanionContextBuilder,
        tool_registry: ToolRegistry,
        *,
        allowed_tools: tuple[str, ...] = (
            "search_previous_chapters",
            "search_vocabulary_history",
        ),
        max_tool_calls: int = 4,
        max_model_turns_per_run: int = 5,
    ):
        if not allowed_tools:
            raise ValueError("allowed_tools must not be empty")
        if max_tool_calls < 1:
            raise ValueError("max_tool_calls must be at least 1")
        if max_model_turns_per_run < 1:
            raise ValueError("max_model_turns_per_run must be at least 1")
        self.provider = provider
        self.context_builder = context_builder
        self.tool_registry = tool_registry
        self.allowed_tools = allowed_tools
        self.provider_tools = tool_registry.provider_tools(allowed_tools)
        self.max_tool_calls = max_tool_calls
        self.max_model_turns_per_run = max_model_turns_per_run

    async def run(
        self,
        state: ReadingCompanionRunState,
        *,
        tool_context: AgentToolExecutionContext,
        book_title: str,
        chapter_title: str,
        chapter_no: int,
        user_message: str | None = None,
        conversation_memory: str = "",
    ) -> ReadingCompanionReply:
        """Advance one user turn through zero or more bounded tool calls."""
        self._validate_tool_context(state, tool_context, chapter_no)
        state = self._accept_user_message(state, user_message)

        for _ in range(self.max_model_turns_per_run):
            observation = ReadingCompanionObservation(
                state=state,
                book_title=book_title,
                chapter_title=chapter_title,
                chapter_no=chapter_no,
                remaining_tool_calls=max(
                    0,
                    self.max_tool_calls - state.tool_call_count,
                ),
                conversation_memory=conversation_memory,
            )
            try:
                response = await self.provider.chat_with_retry(
                    self.context_builder.build(observation),
                    tools=self.provider_tools,
                )
            except Exception:
                logger.exception(
                    "reading companion provider failed episode=%s",
                    state.episode.episode_id,
                )
                return self._recoverable_reply(state, "model_error")

            if response.is_error:
                return self._recoverable_reply(state, "model_error")
            if not response.content and not response.tool_calls:
                return self._recoverable_reply(
                    state,
                    "invalid_model_response",
                    "阅读助手没有返回可用内容，请稍后重试。",
                )

            assistant = self._message(
                state,
                ReadingCompanionMessageRole.ASSISTANT,
                content=response.content or "",
                tool_calls=response.tool_calls,
            )
            state = self._append(state, assistant)
            if not response.tool_calls:
                return ReadingCompanionReply(
                    state=replace(state, error_code=""),
                    message=response.content or "",
                )

            if response.finish_reason == "length":
                for tool_call in response.tool_calls:
                    state = self._append_tool_result(
                        state,
                        tool_call,
                        {
                            "ok": False,
                            "error": "truncated_tool_call",
                        },
                    )
                continue

            for tool_call in response.tool_calls:
                state = await self._execute_tool_call(
                    state,
                    tool_call,
                    tool_context,
                )

        return self._pause_reply(
            state,
            "turn_limit_reached",
            "阅读助手暂时没有完成这次查找，你可以换一种说法继续问我。",
        )

    def _accept_user_message(
        self,
        state: ReadingCompanionRunState,
        user_message: str | None,
    ) -> ReadingCompanionRunState:
        last_role = state.conversation[-1].role
        if user_message is None:
            if last_role is not ReadingCompanionMessageRole.USER:
                raise ReadingCompanionStateError(
                    "a completed companion turn requires a new user message"
                )
            return replace(state, error_code="")
        if not isinstance(user_message, str) or not user_message.strip():
            raise ValueError("user_message must not be empty")
        if last_role is not ReadingCompanionMessageRole.ASSISTANT:
            raise ReadingCompanionStateError(
                "cannot append a user message before the prior turn completes"
            )
        state = self._append(
            state,
            self._message(
                state,
                ReadingCompanionMessageRole.USER,
                content=user_message,
            ),
        )
        return replace(state, tool_call_count=0, error_code="")

    @staticmethod
    def _validate_tool_context(
        state: ReadingCompanionRunState,
        tool_context: AgentToolExecutionContext,
        chapter_no: int,
    ) -> None:
        episode = state.episode
        scope = tool_context.previous_reading_scope
        if (
            tool_context.session_id != episode.session_id
            or tool_context.episode_id != episode.episode_id
            or scope is None
            or scope.book_id != episode.book_id
            or scope.current_chapter_id != episode.chapter_id
            or scope.current_chapter_no != chapter_no
        ):
            raise ReadingCompanionStateError(
                "tool context does not match the active reading episode"
            )

    async def _execute_tool_call(
        self,
        state: ReadingCompanionRunState,
        tool_call: LLMToolCall,
        tool_context: AgentToolExecutionContext,
    ) -> ReadingCompanionRunState:
        if state.tool_call_count >= self.max_tool_calls:
            return self._append_tool_result(
                state,
                tool_call,
                {"ok": False, "error": "tool_call_limit_reached"},
            )
        if tool_call.arguments_error:
            return self._append_tool_result(
                state,
                tool_call,
                {
                    "ok": False,
                    "error": "invalid_tool_arguments",
                },
            )

        state = replace(
            state,
            tool_call_count=state.tool_call_count + 1,
        )
        try:
            result = await self.tool_registry.execute(
                tool_call.name,
                tool_call.arguments,
                allowed_tools=self.allowed_tools,
                context=tool_context,
            )
        except UnknownAgentToolError:
            result = {"ok": False, "error": "unknown_tool"}
        except AgentToolNotAllowedError:
            result = {"ok": False, "error": "tool_not_allowed"}
        except (TypeError, ValueError):
            result = {"ok": False, "error": "invalid_tool_arguments"}
        except Exception:
            logger.exception(
                "reading companion tool failed tool=%s call_id=%s",
                tool_call.name,
                tool_call.id,
            )
            result = {"ok": False, "error": "tool_unavailable"}
        return self._append_tool_result(state, tool_call, result)

    def _append_tool_result(
        self,
        state: ReadingCompanionRunState,
        tool_call: LLMToolCall,
        result: dict[str, object],
    ) -> ReadingCompanionRunState:
        content = json.dumps(
            result,
            ensure_ascii=False,
            sort_keys=True,
        )
        return self._append(
            state,
            self._message(
                state,
                ReadingCompanionMessageRole.TOOL,
                content=content,
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                is_error=result.get("ok") is False,
            ),
        )

    @staticmethod
    def _append(
        state: ReadingCompanionRunState,
        message: ReadingCompanionMessage,
    ) -> ReadingCompanionRunState:
        return replace(
            state,
            conversation=(*state.conversation, message),
        )

    @staticmethod
    def _message(
        state: ReadingCompanionRunState,
        role: ReadingCompanionMessageRole,
        *,
        content: str = "",
        tool_calls: tuple[LLMToolCall, ...] = (),
        tool_call_id: str = "",
        tool_name: str = "",
        is_error: bool = False,
    ) -> ReadingCompanionMessage:
        return ReadingCompanionMessage(
            message_id=uuid4().hex,
            session_id=state.episode.session_id,
            episode_id=state.episode.episode_id,
            role=role,
            content=content,
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            is_error=is_error,
        )

    @staticmethod
    def _recoverable_reply(
        state: ReadingCompanionRunState,
        error_code: str,
        message: str = "阅读助手暂时无法继续思考，请稍后重试。",
    ) -> ReadingCompanionReply:
        state = replace(state, error_code=error_code)
        return ReadingCompanionReply(
            state=state,
            message=message,
            error_code=error_code,
        )

    def _pause_reply(
        self,
        state: ReadingCompanionRunState,
        error_code: str,
        message: str,
    ) -> ReadingCompanionReply:
        state = self._append(
            state,
            self._message(
                state,
                ReadingCompanionMessageRole.ASSISTANT,
                content=message,
            ),
        )
        state = replace(state, error_code=error_code)
        return ReadingCompanionReply(
            state=state,
            message=message,
            error_code=error_code,
        )
