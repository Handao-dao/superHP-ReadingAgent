"""Bounded Agent loop for initial and difficulty-triggered book selection.

The loop lets a model choose whether to ask the reader, search the local
catalog, or finalize recommendations. Deterministic guards own tool budgets,
candidate provenance, state transitions, and failure handling.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Protocol
from uuid import uuid4

from superhp_agent.contracts import (
    BookSearchQuery,
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
from superhp_agent.ports import RecommendationAgentModel


class BookCatalogTool(Protocol):
    """The one concrete capability available to this Agent."""

    async def run(
        self,
        *,
        lexile_min: int | None = None,
        lexile_max: int | None = None,
        genres=(),
        entry_kinds=(),
        excluded_ids=(),
        limit: int = 5,
    ) -> dict[str, object]: ...


class RecommendationAgentStateError(RuntimeError):
    """Raised when a caller attempts an invalid session transition."""


class BookRecommendationAgent:
    """Run bounded observe-decide-act cycles over one catalog tool."""

    def __init__(
        self,
        model: RecommendationAgentModel,
        catalog_tool: BookCatalogTool,
        *,
        max_tool_calls: int = 3,
        max_decisions_per_run: int = 5,
        max_candidates_per_search: int = 10,
    ):
        if max_tool_calls < 1:
            raise ValueError("max_tool_calls must be at least 1")
        if max_decisions_per_run < 1:
            raise ValueError("max_decisions_per_run must be at least 1")
        if max_candidates_per_search < 1:
            raise ValueError("max_candidates_per_search must be at least 1")
        self.model = model
        self.catalog_tool = catalog_tool
        self.max_tool_calls = max_tool_calls
        self.max_decisions_per_run = max_decisions_per_run
        self.max_candidates_per_search = max_candidates_per_search

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
                decision = await self.model.decide(observation)
            except Exception:
                return self._failed_reply(
                    session,
                    message="选书助手暂时无法继续思考，请稍后重试。",
                    error_code="model_error",
                )
            if not isinstance(decision, RecommendationAgentDecision):
                return self._failed_reply(
                    session,
                    message="选书助手返回了无法识别的决策，请稍后重试。",
                    error_code="invalid_model_decision",
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

            if decision.kind is RecommendationAgentDecisionKind.SEARCH_CATALOG:
                session = await self._search(session, decision.search_query)
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

    async def _search(
        self,
        session: RecommendationAgentSession,
        query: BookSearchQuery | None,
    ) -> RecommendationAgentSession:
        if query is None:
            return self._append_tool_observation(
                session,
                {"ok": False, "error": "missing_search_query"},
            )
        if session.tool_call_count >= self.max_tool_calls:
            return self._append_tool_observation(
                session,
                {"ok": False, "error": "tool_call_limit_reached"},
            )

        next_count = session.tool_call_count + 1
        session = replace(
            session,
            phase=RecommendationAgentPhase.SEARCHING,
            tool_call_count=next_count,
        )
        if query.limit > self.max_candidates_per_search:
            return self._append_tool_observation(
                session,
                {
                    "ok": False,
                    "error": "candidate_limit_too_large",
                    "maximum": self.max_candidates_per_search,
                },
            )

        try:
            result = await self.catalog_tool.run(
                lexile_min=query.lexile_min,
                lexile_max=query.lexile_max,
                genres=query.categories,
                entry_kinds=tuple(kind.value for kind in query.entry_kinds),
                excluded_ids=query.excluded_ids,
                limit=query.limit,
            )
        except ValueError as exc:
            return self._append_tool_observation(
                session,
                {"ok": False, "error": "invalid_search", "detail": str(exc)},
            )
        except Exception:
            return self._append_tool_observation(
                session,
                {"ok": False, "error": "catalog_unavailable"},
            )

        observed_ids = _merge_unique(
            session.observed_catalog_ids,
            _catalog_ids_from_result(result),
        )
        session = replace(session, observed_catalog_ids=observed_ids)
        return self._append_tool_observation(
            session,
            {"ok": True, "result": result},
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
