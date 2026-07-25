"""Small explicit registry for tools available to an Agent loop.

Registration and authorization are separate: a tool may exist in the
application without being exposed to every Agent. The registry deliberately
does not scan plugins, own business rules, or decide when a tool should run.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Protocol, runtime_checkable


@runtime_checkable
class AgentTool(Protocol):
    """One JSON-described capability callable by an Agent loop."""

    name: str
    description: str
    input_schema: Mapping[str, object]

    async def run(self, **arguments: object) -> dict[str, object]: ...


class UnknownAgentToolError(LookupError):
    """Raised when a tool name has not been registered."""


class AgentToolNotAllowedError(PermissionError):
    """Raised when the current Agent was not granted a registered tool."""


class ToolRegistry:
    """Register, describe, and execute a small set of explicit Agent tools."""

    def __init__(self, tools: Iterable[AgentTool] = ()):
        self._tools: dict[str, AgentTool] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: AgentTool) -> None:
        """Register one tool and reject ambiguous duplicate names."""
        name = tool.name.strip()
        if not name:
            raise ValueError("tool name must not be empty")
        if name in self._tools:
            raise ValueError(f"tool already registered: {name}")
        self._tools[name] = tool

    def describe(self, allowed_tools: Iterable[str]) -> list[dict[str, object]]:
        """Return model-facing descriptions in caller-specified order."""
        descriptions: list[dict[str, object]] = []
        for name in _unique_names(allowed_tools):
            tool = self._get(name)
            descriptions.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": dict(tool.input_schema),
                }
            )
        return descriptions

    async def execute(
        self,
        tool_name: str,
        arguments: Mapping[str, object],
        *,
        allowed_tools: Iterable[str],
    ) -> dict[str, object]:
        """Execute one registered and explicitly allowed tool."""
        tool = self._get(tool_name)
        allowed = set(_unique_names(allowed_tools))
        if tool_name not in allowed:
            raise AgentToolNotAllowedError(
                f"tool is not allowed for this agent: {tool_name}"
            )
        result = await tool.run(**dict(arguments))
        if not isinstance(result, dict):
            raise TypeError(f"tool {tool_name!r} returned a non-object result")
        return result

    def _get(self, tool_name: str) -> AgentTool:
        try:
            return self._tools[tool_name]
        except KeyError as exc:
            raise UnknownAgentToolError(
                f"unknown agent tool: {tool_name}"
            ) from exc


def _unique_names(names: Iterable[str]) -> tuple[str, ...]:
    values: list[str] = []
    seen: set[str] = set()
    for name in names:
        clean_name = name.strip()
        if not clean_name or clean_name in seen:
            continue
        seen.add(clean_name)
        values.append(clean_name)
    return tuple(values)
