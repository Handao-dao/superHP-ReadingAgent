"""Bounded Agent loop for conversational English-book recommendation.

The loop directly composes the existing ContextBuilder pattern, LLM Provider,
and an explicitly authorized ToolRegistry. It owns only the repeated
observe-decide-act control flow and its small safety budget.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from uuid import uuid4

from superhp_agent.agent_tools import (
    AgentToolNotAllowedError,
    ToolRegistry,
    UnknownAgentToolError,
)
from superhp_agent.agents.recommendation_context import (
    RecommendationContextBuilder,
)
from superhp_agent.contracts import (
    RecommendationAgentDecision,
    RecommendationAgentDecisionKind,
    RecommendationAgentMessage,
    RecommendationAgentMessageRole,
    RecommendationAgentObservation,
    RecommendationAgentPhase,
    RecommendationAgentReply,
    RecommendationAgentSession,
    RecommendationRequest,
)
from superhp_agent.ports import LLMProvider


class RecommendationAgentStateError(RuntimeError):
    """Raised when a caller attempts an invalid session transition."""


class RecommendationDecisionParseError(ValueError):
    """Raised when model text cannot be normalized into one valid decision."""


class RecommendationModelCallError(RuntimeError):
    """Raised when the Provider cannot return usable model text."""


class BookRecommendationAgent:
    """Run a bounded observe-decide-act loop over explicitly allowed tools."""

    def __init__(
        self,
        provider: LLMProvider,
        context_builder: RecommendationContextBuilder,
        tool_registry: ToolRegistry,
        *,
        allowed_tools: tuple[str, ...] = ("search_local_book_catalog",),
        max_tool_calls: int = 3,
        max_decisions_per_run: int = 5,
    ):
        if not allowed_tools:
            raise ValueError("allowed_tools must not be empty")
        if max_tool_calls < 1:
            raise ValueError("max_tool_calls must be at least 1")
        if max_decisions_per_run < 1:
            raise ValueError("max_decisions_per_run must be at least 1")
        # Resolve descriptions now so missing tool registrations fail during
        # composition rather than halfway through a user conversation.
        self.tool_descriptions = tool_registry.describe(allowed_tools)
        self.provider = provider
        self.context_builder = context_builder
        self.tool_registry = tool_registry
        self.allowed_tools = allowed_tools
        self.max_tool_calls = max_tool_calls
        self.max_decisions_per_run = max_decisions_per_run

    def start(
        self,
        request: RecommendationRequest,
        *,
        session_id: str | None = None,
    ) -> RecommendationAgentSession:
        """Create a fresh, inactive session without calling the model."""
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
        """Advance until the loop pauses, completes, or reaches a guard."""
        session = self._accept_user_message(session, user_message)

        for _ in range(self.max_decisions_per_run):
            observation = RecommendationAgentObservation(
                request=session.request,
                phase=session.phase,
                conversation=session.conversation,
                observed_catalog_ids=session.observed_catalog_ids,
                remaining_tool_calls=max(
                    0,
                    self.max_tool_calls - session.tool_call_count,
                ),
            )
            try:
                decision = await self._decide(observation)
            except RecommendationDecisionParseError:
                return self._failed_reply(
                    session,
                    message="选书助手返回了无法识别的决策，请稍后重试。",
                    error_code="invalid_model_decision",
                )
            except Exception:
                return self._failed_reply(
                    session,
                    message="选书助手暂时无法继续思考，请稍后重试。",
                    error_code="model_error",
                )

            if decision.kind is RecommendationAgentDecisionKind.ASK_USER:
                session = self._append_message(
                    session,
                    RecommendationAgentMessageRole.ASSISTANT,
                    decision.message,
                    phase=RecommendationAgentPhase.AWAITING_USER,
                )
                return RecommendationAgentReply(
                    session=session,
                    message=decision.message,
                )

            if decision.kind is RecommendationAgentDecisionKind.CALL_TOOL:
                session = await self._call_tool(session, decision)
                continue

            unknown_ids = tuple(
                catalog_id
                for catalog_id in decision.recommended_catalog_ids
                if catalog_id not in session.observed_catalog_ids
            )
            if unknown_ids:
                session = self._append_tool_observation(
                    session,
                    {
                        "ok": False,
                        "error": "unobserved_recommendation_ids",
                        "catalog_ids": list(unknown_ids),
                    },
                )
                continue

            session = self._append_message(
                session,
                RecommendationAgentMessageRole.ASSISTANT,
                decision.message,
                phase=RecommendationAgentPhase.COMPLETED,
            )
            return RecommendationAgentReply(
                session=session,
                message=decision.message,
                recommended_catalog_ids=decision.recommended_catalog_ids,
            )

        return self._failed_reply(
            session,
            message="选书助手未能在限定步骤内完成推荐，请补充偏好后重试。",
            error_code="decision_limit_reached",
        )

    async def _decide(
        self,
        observation: RecommendationAgentObservation,
    ) -> RecommendationAgentDecision:
        messages = self.context_builder.build(
            observation,
            self.tool_descriptions,
        )
        response = await self.provider.chat_with_retry(messages)
        if response.is_error or not response.content:
            raise RecommendationModelCallError("provider returned no usable content")
        return _parse_decision(response.content)

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
            return session
        if not user_message.strip():
            raise ValueError("user_message must not be empty")
        return self._append_message(
            session,
            RecommendationAgentMessageRole.USER,
            user_message,
            phase=RecommendationAgentPhase.COLLECTING_PREFERENCES,
        )

    async def _call_tool(
        self,
        session: RecommendationAgentSession,
        decision: RecommendationAgentDecision,
    ) -> RecommendationAgentSession:
        if session.tool_call_count >= self.max_tool_calls:
            return self._append_tool_observation(
                session,
                {
                    "ok": False,
                    "tool": decision.tool_name,
                    "arguments": decision.tool_arguments,
                    "error": "tool_call_limit_reached",
                },
            )

        session = replace(
            session,
            phase=RecommendationAgentPhase.SEARCHING,
            tool_call_count=session.tool_call_count + 1,
        )
        try:
            result = await self.tool_registry.execute(
                decision.tool_name,
                decision.tool_arguments,
                allowed_tools=self.allowed_tools,
            )
        except UnknownAgentToolError:
            return self._append_tool_observation(
                session,
                {
                    "ok": False,
                    "tool": decision.tool_name,
                    "arguments": decision.tool_arguments,
                    "error": "unknown_tool",
                },
            )
        except AgentToolNotAllowedError:
            return self._append_tool_observation(
                session,
                {
                    "ok": False,
                    "tool": decision.tool_name,
                    "arguments": decision.tool_arguments,
                    "error": "tool_not_allowed",
                },
            )
        except (TypeError, ValueError) as exc:
            return self._append_tool_observation(
                session,
                {
                    "ok": False,
                    "tool": decision.tool_name,
                    "arguments": decision.tool_arguments,
                    "error": "invalid_tool_arguments",
                    "detail": str(exc),
                },
            )
        except Exception:
            return self._append_tool_observation(
                session,
                {
                    "ok": False,
                    "tool": decision.tool_name,
                    "arguments": decision.tool_arguments,
                    "error": "tool_unavailable",
                },
            )

        observed_ids = _merge_unique(
            session.observed_catalog_ids,
            _catalog_ids_from_result(result),
        )
        session = replace(session, observed_catalog_ids=observed_ids)
        return self._append_tool_observation(
            session,
            {
                "ok": True,
                "tool": decision.tool_name,
                "arguments": decision.tool_arguments,
                "result": result,
            },
        )

    @staticmethod
    def _append_message(
        session: RecommendationAgentSession,
        role: RecommendationAgentMessageRole,
        content: str,
        *,
        phase: RecommendationAgentPhase | None = None,
    ) -> RecommendationAgentSession:
        return replace(
            session,
            phase=phase or session.phase,
            conversation=(
                *session.conversation,
                RecommendationAgentMessage(role=role, content=content),
            ),
        )

    def _append_tool_observation(
        self,
        session: RecommendationAgentSession,
        payload: dict[str, object],
    ) -> RecommendationAgentSession:
        return self._append_message(
            session,
            RecommendationAgentMessageRole.TOOL,
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            phase=RecommendationAgentPhase.SEARCHING,
        )

    def _failed_reply(
        self,
        session: RecommendationAgentSession,
        *,
        message: str,
        error_code: str,
    ) -> RecommendationAgentReply:
        session = self._append_message(
            session,
            RecommendationAgentMessageRole.ASSISTANT,
            message,
            phase=RecommendationAgentPhase.FAILED,
        )
        return RecommendationAgentReply(
            session=session,
            message=message,
            error_code=error_code,
        )


def _parse_decision(content: str) -> RecommendationAgentDecision:
    try:
        payload = _extract_json_object(content)
        action = RecommendationAgentDecisionKind(payload.get("action"))
        if action is RecommendationAgentDecisionKind.ASK_USER:
            return RecommendationAgentDecision(
                kind=action,
                message=_required_string(payload, "message"),
            )
        if action is RecommendationAgentDecisionKind.CALL_TOOL:
            arguments = payload.get("arguments", {})
            if not isinstance(arguments, dict):
                raise ValueError("arguments must be an object")
            return RecommendationAgentDecision(
                kind=action,
                tool_name=_required_string(payload, "tool_name"),
                tool_arguments=arguments,
            )
        catalog_ids = payload.get("recommended_catalog_ids")
        if not isinstance(catalog_ids, list) or not all(
            isinstance(value, str) for value in catalog_ids
        ):
            raise ValueError("recommended_catalog_ids must be a string array")
        return RecommendationAgentDecision(
            kind=action,
            message=_required_string(payload, "message"),
            recommended_catalog_ids=tuple(catalog_ids),
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RecommendationDecisionParseError(str(exc)) from exc


def _extract_json_object(content: str) -> Mapping[str, object]:
    start = content.find("{")
    if start < 0:
        raise ValueError("model response does not contain a JSON object")
    payload, _ = json.JSONDecoder().raw_decode(content[start:])
    if not isinstance(payload, dict):
        raise ValueError("model response JSON must be an object")
    return payload


def _required_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


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
