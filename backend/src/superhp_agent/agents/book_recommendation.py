"""Message-driven Agent loop for conversational book recommendation.

Like pi's low-level loop, this module owns only observe-model-tool repetition.
Completed user, assistant, and tool messages remain in the Session; storage,
transport, streaming UI, and long-term recovery stay outside the loop.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace
from uuid import uuid4

from superhp_agent.agent_tools.registry import (
    AgentToolNotAllowedError,
    ToolRegistry,
    UnknownAgentToolError,
)
from superhp_agent.agents.recommendation_context import (
    RecommendationContextBuilder,
)
from superhp_agent.contracts import (
    LLMToolCall,
    RecommendationAgentMessage,
    RecommendationAgentMessageRole,
    RecommendationAgentObservation,
    RecommendationAgentPhase,
    RecommendationAgentReply,
    RecommendationAgentSession,
    RecommendationRequest,
)
from superhp_agent.ports import LLMProvider

logger = logging.getLogger(__name__)


class RecommendationAgentStateError(RuntimeError):
    """Raised when a caller attempts an invalid session transition."""


@dataclass(frozen=True)
class _TerminalRecommendation:
    message: str
    selected_catalog_id: str


@dataclass(frozen=True)
class _PresentedRecommendations:
    message: str
    catalog_ids: tuple[str, ...]


class BookRecommendationAgent:
    """Run model turns until normal text pauses or a terminal tool completes."""

    def __init__(
        self,
        provider: LLMProvider,
        context_builder: RecommendationContextBuilder,
        tool_registry: ToolRegistry,
        *,
        allowed_tools: tuple[str, ...] = (
            "search_local_book_catalog",
            "present_book_recommendations",
            "select_recommended_book",
        ),
        max_tool_calls: int = 3,
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

    def start(
        self,
        request: RecommendationRequest,
        *,
        session_id: str | None = None,
    ) -> RecommendationAgentSession:
        """Create a fresh session without calling the model."""
        return RecommendationAgentSession(
            session_id=session_id or uuid4().hex,
            request=request,
        )

    async def run(
        self,
        session: RecommendationAgentSession,
        *,
        user_message: str | None = None,
    ) -> RecommendationAgentReply:
        """Advance until normal text, a terminal tool, or a safety guard."""
        session = self._accept_user_message(session, user_message)

        for model_turn in range(1, self.max_model_turns_per_run + 1):
            observation = RecommendationAgentObservation(
                request=session.request,
                phase=session.phase,
                conversation=session.conversation,
                observed_catalog_ids=session.observed_catalog_ids,
                presented_catalog_ids=session.recommended_catalog_ids,
                selected_catalog_id=session.selected_catalog_id,
                context_start_index=session.context_start_index,
                remaining_tool_calls=max(
                    0,
                    self.max_tool_calls - session.tool_call_count,
                ),
            )
            provider_messages = self.context_builder.build(observation)
            logger.debug(
                "recommendation context session=%s model_turn=%s "
                "messages=%s characters=%s",
                session.session_id,
                model_turn,
                len(provider_messages),
                _context_character_count(provider_messages),
            )
            try:
                response = await self.provider.chat_with_retry(
                    provider_messages,
                    tools=self.provider_tools,
                )
            except Exception:
                logger.exception(
                    "recommendation provider failed session=%s",
                    session.session_id,
                )
                return self._recoverable_reply(
                    session,
                    error_code="model_error",
                )

            if response.is_error:
                logger.warning(
                    "recommendation provider exhausted retries "
                    "session=%s kind=%s status=%s code=%s",
                    session.session_id,
                    response.error_kind,
                    response.error_status_code,
                    response.error_code,
                )
                return self._recoverable_reply(
                    session,
                    error_code="model_error",
                )
            if not response.content and not response.tool_calls:
                return self._recoverable_reply(
                    session,
                    error_code="invalid_model_response",
                    message="选书助手没有返回可用内容，请稍后重试。",
                )

            assistant_message = RecommendationAgentMessage(
                role=RecommendationAgentMessageRole.ASSISTANT,
                content=response.content or "",
                tool_calls=response.tool_calls,
            )
            if not response.tool_calls:
                session = self._append_message(
                    session,
                    assistant_message,
                    phase=RecommendationAgentPhase.AWAITING_USER,
                )
                return RecommendationAgentReply(
                    session=session,
                    message=response.content or "",
                )

            session = self._append_message(
                session,
                assistant_message,
                phase=RecommendationAgentPhase.SEARCHING,
            )
            if response.finish_reason == "length":
                for tool_call in response.tool_calls:
                    session = self._append_tool_result(
                        session,
                        tool_call,
                        {
                            "ok": False,
                            "error": "truncated_tool_call",
                            "detail": (
                                "Tool call was not executed because the model "
                                "response reached its output limit."
                            ),
                        },
                        is_error=True,
                    )
                continue
            session, presentation, terminal = await self._execute_tool_calls(
                session,
                response.tool_calls,
            )
            if terminal is not None:
                session = self._append_message(
                    session,
                    RecommendationAgentMessage(
                        role=RecommendationAgentMessageRole.ASSISTANT,
                        content=terminal.message,
                    ),
                    phase=RecommendationAgentPhase.COMPLETED,
                )
                session = replace(
                    session,
                    selected_catalog_id=terminal.selected_catalog_id,
                )
                return RecommendationAgentReply(
                    session=session,
                    message=terminal.message,
                    recommended_catalog_ids=(
                        session.recommended_catalog_ids
                    ),
                )
            if presentation is not None:
                session = self._append_message(
                    session,
                    RecommendationAgentMessage(
                        role=RecommendationAgentMessageRole.ASSISTANT,
                        content=presentation.message,
                    ),
                    phase=RecommendationAgentPhase.AWAITING_USER,
                )
                session = replace(
                    session,
                    recommended_catalog_ids=presentation.catalog_ids,
                    selected_catalog_id="",
                )
                return RecommendationAgentReply(
                    session=session,
                    message=presentation.message,
                    recommended_catalog_ids=presentation.catalog_ids,
                )

        return self._pause_reply(
            session,
            error_code="turn_limit_reached",
            message="选书助手未能在限定步骤内完成推荐，请补充偏好后重试。",
        )

    def _accept_user_message(
        self,
        session: RecommendationAgentSession,
        user_message: str | None,
    ) -> RecommendationAgentSession:
        if session.phase in {
            RecommendationAgentPhase.COMPLETED,
            RecommendationAgentPhase.FAILED,
        }:
            raise RecommendationAgentStateError(
                f"cannot continue a {session.phase.value} recommendation session"
            )
        if session.phase is RecommendationAgentPhase.AWAITING_USER:
            if user_message is None or not user_message.strip():
                raise RecommendationAgentStateError(
                    "awaiting_user session requires a user message"
                )
        if user_message is None:
            return replace(session, error_code="")
        if not user_message.strip():
            raise ValueError("user_message must not be empty")
        accepted = self._append_message(
            session,
            RecommendationAgentMessage(
                role=RecommendationAgentMessageRole.USER,
                content=user_message,
            ),
            phase=RecommendationAgentPhase.COLLECTING_PREFERENCES,
        )
        return replace(accepted, tool_call_count=0, error_code="")

    async def _execute_tool_calls(
        self,
        session: RecommendationAgentSession,
        tool_calls: tuple[LLMToolCall, ...],
    ) -> tuple[
        RecommendationAgentSession,
        _PresentedRecommendations | None,
        _TerminalRecommendation | None,
    ]:
        observed_before_turn = set(session.observed_catalog_ids)
        presented_before_turn = set(session.recommended_catalog_ids)
        presentation: _PresentedRecommendations | None = None
        terminal: _TerminalRecommendation | None = None

        for tool_call in tool_calls:
            if session.tool_call_count >= self.max_tool_calls:
                session = self._append_tool_result(
                    session,
                    tool_call,
                    {
                        "ok": False,
                        "error": "tool_call_limit_reached",
                    },
                    is_error=True,
                )
                continue

            session = replace(
                session,
                tool_call_count=session.tool_call_count + 1,
            )
            result, error = await self._execute_one_tool(tool_call)
            if error is not None:
                session = self._append_tool_result(
                    session,
                    tool_call,
                    error,
                    is_error=True,
                )
                continue

            assert result is not None
            candidate_ids = _catalog_ids_from_result(result)
            session = replace(
                session,
                observed_catalog_ids=_merge_unique(
                    session.observed_catalog_ids,
                    candidate_ids,
                ),
            )

            presentation_result, terminal_result, action_error = (
                _recommendation_action_from_result(
                    result,
                    observed_before_turn,
                    presented_before_turn,
                )
            )
            if action_error is not None:
                session = self._append_tool_result(
                    session,
                    tool_call,
                    action_error,
                    is_error=True,
                )
                continue

            session = self._append_tool_result(
                session,
                tool_call,
                {"ok": True, "result": result},
            )
            if presentation_result is not None and presentation is None:
                presentation = presentation_result
            if terminal_result is not None and terminal is None:
                terminal = terminal_result

        return session, presentation, terminal

    async def _execute_one_tool(
        self,
        tool_call: LLMToolCall,
    ) -> tuple[dict[str, object] | None, dict[str, object] | None]:
        if tool_call.arguments_error:
            return None, {
                "ok": False,
                "error": "invalid_tool_arguments",
                "detail": tool_call.arguments_error,
            }
        try:
            result = await self.tool_registry.execute(
                tool_call.name,
                tool_call.arguments,
                allowed_tools=self.allowed_tools,
            )
            return result, None
        except UnknownAgentToolError:
            return None, {"ok": False, "error": "unknown_tool"}
        except AgentToolNotAllowedError:
            return None, {"ok": False, "error": "tool_not_allowed"}
        except (TypeError, ValueError) as exc:
            return None, {
                "ok": False,
                "error": "invalid_tool_arguments",
                "detail": str(exc),
            }
        except Exception:
            logger.exception(
                "recommendation tool failed tool=%s call_id=%s",
                tool_call.name,
                tool_call.id,
            )
            return None, {"ok": False, "error": "tool_unavailable"}

    @staticmethod
    def _append_message(
        session: RecommendationAgentSession,
        message: RecommendationAgentMessage,
        *,
        phase: RecommendationAgentPhase | None = None,
    ) -> RecommendationAgentSession:
        return replace(
            session,
            phase=phase or session.phase,
            conversation=(*session.conversation, message),
        )

    def _append_tool_result(
        self,
        session: RecommendationAgentSession,
        tool_call: LLMToolCall,
        payload: dict[str, object],
        *,
        is_error: bool = False,
    ) -> RecommendationAgentSession:
        return self._append_message(
            session,
            RecommendationAgentMessage(
                role=RecommendationAgentMessageRole.TOOL,
                content=json.dumps(
                    {
                        "tool": tool_call.name,
                        **payload,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                is_error=is_error,
            ),
            phase=RecommendationAgentPhase.SEARCHING,
        )

    @staticmethod
    def _recoverable_reply(
        session: RecommendationAgentSession,
        *,
        error_code: str,
        message: str = "选书助手暂时无法继续思考，请稍后重试。",
    ) -> RecommendationAgentReply:
        """Return an operational error without changing the model transcript."""
        session = replace(session, error_code=error_code)
        return RecommendationAgentReply(
            session=session,
            message=message,
            error_code=error_code,
        )

    def _pause_reply(
        self,
        session: RecommendationAgentSession,
        *,
        error_code: str,
        message: str,
    ) -> RecommendationAgentReply:
        """Pause a valid but exhausted turn and ask for new user input."""
        session = self._append_message(
            session,
            RecommendationAgentMessage(
                role=RecommendationAgentMessageRole.ASSISTANT,
                content=message,
            ),
            phase=RecommendationAgentPhase.AWAITING_USER,
        )
        session = replace(session, error_code=error_code)
        return RecommendationAgentReply(
            session=session,
            message=message,
            error_code=error_code,
        )


def _recommendation_action_from_result(
    result: dict[str, object],
    observed_catalog_ids: set[str],
    presented_catalog_ids: set[str],
) -> tuple[
    _PresentedRecommendations | None,
    _TerminalRecommendation | None,
    dict[str, object] | None,
]:
    action = result.get("action")
    if action == "present_recommendations":
        return _presentation_from_result(result, observed_catalog_ids)
    if action == "select_recommended_book":
        return _selection_from_result(result, presented_catalog_ids)
    return None, None, None


def _presentation_from_result(
    result: dict[str, object],
    observed_catalog_ids: set[str],
) -> tuple[
    _PresentedRecommendations | None,
    None,
    dict[str, object] | None,
]:
    catalog_ids = result.get("catalog_ids")
    message = result.get("message")
    if not isinstance(catalog_ids, list) or not all(
        isinstance(catalog_id, str) for catalog_id in catalog_ids
    ):
        return None, None, {
            "ok": False,
            "error": "invalid_presentation_result",
        }
    unknown_ids = [
        catalog_id
        for catalog_id in catalog_ids
        if catalog_id not in observed_catalog_ids
    ]
    if unknown_ids:
        return None, None, {
            "ok": False,
            "error": "unobserved_recommendation_ids",
            "catalog_ids": unknown_ids,
        }
    if not isinstance(message, str) or not message.strip():
        return None, None, {
            "ok": False,
            "error": "invalid_presentation_result",
        }
    return (
        _PresentedRecommendations(
            message=message,
            catalog_ids=tuple(catalog_ids),
        ),
        None,
        None,
    )


def _selection_from_result(
    result: dict[str, object],
    presented_catalog_ids: set[str],
) -> tuple[
    None,
    _TerminalRecommendation | None,
    dict[str, object] | None,
]:
    catalog_id = result.get("catalog_id")
    message = result.get("message")
    if not isinstance(catalog_id, str) or not catalog_id.strip():
        return None, None, {
            "ok": False,
            "error": "invalid_selection_result",
        }
    if catalog_id not in presented_catalog_ids:
        return None, None, {
            "ok": False,
            "error": "unpresented_selection_id",
            "catalog_id": catalog_id,
        }
    if not isinstance(message, str) or not message.strip():
        return None, None, {
            "ok": False,
            "error": "invalid_selection_result",
        }
    return (
        None,
        _TerminalRecommendation(
            message=message,
            selected_catalog_id=catalog_id,
        ),
        None,
    )


def _catalog_ids_from_result(result: dict[str, object]) -> tuple[str, ...]:
    candidates = result.get("candidates")
    if not isinstance(candidates, list):
        return ()
    catalog_ids: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        catalog_id = candidate.get("catalog_id")
        if isinstance(catalog_id, str) and catalog_id:
            catalog_ids.append(catalog_id)
    return tuple(catalog_ids)


def _merge_unique(existing: tuple[str, ...], added: tuple[str, ...]) -> tuple[str, ...]:
    values = list(existing)
    seen = set(existing)
    for value in added:
        if value in seen:
            continue
        seen.add(value)
        values.append(value)
    return tuple(values)


def _context_character_count(messages: list[dict[str, object]]) -> int:
    """Return a stable coarse context-size metric without tokenization cost."""
    return sum(
        len(json.dumps(message, ensure_ascii=False, sort_keys=True))
        for message in messages
    )
