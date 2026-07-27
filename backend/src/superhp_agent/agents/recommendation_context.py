"""Prompt and native message context for book recommendation.

Stable rules are built once per request while the transcript remains a real
user/assistant/tool sequence. The builder does not call models or tools.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from superhp_agent.context import ContextBlock, ContextBundle
from superhp_agent.contracts import (
    RecommendationAgentMessage,
    RecommendationAgentMessageRole,
    RecommendationAgentObservation,
)

_ROLE_AND_RULES = """\
你是英文阅读助手中的选书 Agent。通过简短对话了解用户偏好，使用已授权工具查询真实目录，
最终推荐 1～3 本适合开始阅读的英文书。

必须遵守：
1. 书名、蓝思值和 catalog_id 只能来自工具结果，不得凭记忆编造。
2. 信息不足时，直接用自然语言一次询问一个关键问题，然后停止本轮。
3. 需要候选时调用 search_local_book_catalog；严格匹配无结果时可以调整条件重搜或询问用户。
4. 完成推荐时必须调用 present_book_recommendations，不要只在普通文本里列出最终书目。
5. present_book_recommendations 只能引用当前会话搜索工具已经返回的 catalog_id。
6. 不替用户下载、导入或切换图书，也不启动阅读标注工作流。
7. 每次只调用一个工具，等待工具结果后再决定下一步。
8. 当 request.origin 为 difficulty_alert 时，先根据 handoff 简要说明近期阅读负担，再优先寻找
   比当前作品更容易持续阅读的候选；默认延续原题材，但用户的新偏好优先。"""


class RecommendationContextBuilder:
    """Build Provider messages from one recommendation observation."""

    def build(
        self,
        observation: RecommendationAgentObservation,
    ) -> list[dict[str, Any]]:
        """Return stable instructions, runtime facts, then native transcript."""
        bundle = ContextBundle(
            system_blocks=(
                ContextBlock(
                    name="agent_role_and_rules",
                    content=_ROLE_AND_RULES,
                    role="system",
                ),
            ),
            user_blocks=(
                ContextBlock(
                    name="recommendation_runtime",
                    content=json.dumps(
                        _serialize_runtime(observation),
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    role="metadata",
                    trusted=False,
                ),
            ),
        )
        messages: list[dict[str, Any]] = bundle.to_messages()
        messages.extend(
            _message_to_provider(message)
            for message in observation.conversation
        )
        return messages


def _serialize_runtime(
    observation: RecommendationAgentObservation,
) -> dict[str, object]:
    return {
        "request": asdict(observation.request),
        "phase": observation.phase.value,
        "observed_catalog_ids": list(observation.observed_catalog_ids),
        "remaining_tool_calls": observation.remaining_tool_calls,
    }


def _message_to_provider(
    message: RecommendationAgentMessage,
) -> dict[str, Any]:
    if message.role is RecommendationAgentMessageRole.USER:
        return {"role": "user", "content": message.content}
    if message.role is RecommendationAgentMessageRole.ASSISTANT:
        provider_message: dict[str, Any] = {
            "role": "assistant",
            "content": message.content or None,
        }
        if message.tool_calls:
            provider_message["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": call.raw_arguments
                        or json.dumps(
                            call.arguments,
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                    },
                }
                for call in message.tool_calls
            ]
        return provider_message
    return {
        "role": "tool",
        "tool_call_id": message.tool_call_id,
        "content": message.content,
    }
