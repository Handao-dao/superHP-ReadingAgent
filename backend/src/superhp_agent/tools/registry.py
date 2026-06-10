"""Small tool registry inspired by nanobot's registry shape."""

from __future__ import annotations

from typing import Any

from superhp_agent.tools.base import Tool


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    async def execute(self, name: str, **kwargs: Any) -> Any:
        tool = self.get(name)
        if tool is None:
            raise KeyError(f"Unknown tool: {name}")
        return await tool.execute(**kwargs)

    @property
    def names(self) -> list[str]:
        return sorted(self._tools)
