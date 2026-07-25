"""Prompt context for the bounded book-recommendation Agent.

The builder keeps stable instructions separate from the changing observation.
It does not call the model, execute tools, or choose the next action.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from superhp_agent.context import ContextBlock, ContextBundle
from superhp_agent.contracts import RecommendationAgentObservation

_ROLE_AND_RULES = """\
你是英文阅读助手中的选书 Agent。你的任务是通过简短对话了解用户偏好，
使用已授权工具查询真实目录，并最终推荐 1～3 本合适的英文书。

必须遵守：
1. 书名、蓝思值和 catalog_id 只能来自工具结果，不得凭记忆编造。
2. 信息不足时一次只问一个关键问题，不要把问卷一次全部抛给用户。
3. 工具严格匹配无结果时，可以调整条件再次搜索，或向用户确认是否放宽。
4. finalize 只能引用当前会话工具曾返回的 catalog_id。
5. 不替用户下载、导入、切换图书，也不启动阅读标注工作流。
6. 每次只输出一个 JSON 对象，不要输出 Markdown 或额外解释。"""

_DECISION_PROTOCOL = """\
你每轮只能选择以下一种动作：

询问用户：
{"action":"ask_user","message":"要询问的一个关键问题"}

调用工具：
{"action":"call_tool","tool_name":"工具名称","arguments":{}}

完成推荐：
{"action":"finalize","message":"面向用户的推荐理由","recommended_catalog_ids":["id"]}

finalize 必须返回 1～3 个互不重复、且已由工具返回的 catalog_id。"""


class RecommendationContextBuilder:
    """Build provider messages from one observation and an allowed tool set."""

    def build(
        self,
        observation: RecommendationAgentObservation,
        tool_descriptions: list[dict[str, object]],
    ) -> list[dict[str, Any]]:
        """Return stable instructions followed by dynamic session state."""
        bundle = ContextBundle(
            system_blocks=(
                ContextBlock(
                    name="agent_role_and_rules",
                    content=_ROLE_AND_RULES,
                    role="system",
                ),
                ContextBlock(
                    name="decision_protocol",
                    content=_DECISION_PROTOCOL,
                    role="system",
                ),
                ContextBlock(
                    name="available_tools",
                    content=json.dumps(
                        tool_descriptions,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    role="system",
                ),
            ),
            user_blocks=(
                ContextBlock(
                    name="recommendation_observation",
                    content=json.dumps(
                        _serialize_observation(observation),
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    role="metadata",
                    trusted=False,
                ),
            ),
        )
        return bundle.to_messages()


def _serialize_observation(
    observation: RecommendationAgentObservation,
) -> dict[str, object]:
    return {
        "request": asdict(observation.request),
        "phase": observation.phase.value,
        "conversation": [
            {
                "role": message.role.value,
                "content": message.content,
            }
            for message in observation.conversation
        ],
        "observed_catalog_ids": list(observation.observed_catalog_ids),
        "remaining_tool_calls": observation.remaining_tool_calls,
    }
