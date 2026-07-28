"""Tests for explicit Agent tool registration and authorization."""

import pytest

from superhp_agent.agent_tools import (
    AgentToolNotAllowedError,
    ToolRegistry,
    UnknownAgentToolError,
)
from superhp_agent.contracts import AgentToolExecutionContext


class EchoTool:
    name = "echo"
    description = "Return the supplied text."
    input_schema = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
    }

    def __init__(self):
        self.calls = []

    async def run(self, **arguments):
        self.calls.append(arguments)
        return {"text": arguments["text"]}


@pytest.mark.asyncio
async def test_registry_describes_and_executes_an_allowed_tool():
    tool = EchoTool()
    registry = ToolRegistry((tool,))

    descriptions = registry.describe(("echo",))
    provider_tools = registry.provider_tools(("echo",))
    result = await registry.execute(
        "echo",
        {"text": "hello"},
        allowed_tools=("echo",),
    )

    assert descriptions == [
        {
            "name": "echo",
            "description": "Return the supplied text.",
            "input_schema": EchoTool.input_schema,
        }
    ]
    assert result == {"text": "hello"}
    assert tool.calls == [{"text": "hello"}]
    assert provider_tools == [
        {
            "type": "function",
            "function": {
                "name": "echo",
                "description": "Return the supplied text.",
                "parameters": EchoTool.input_schema,
            },
        }
    ]


def test_registry_rejects_duplicate_and_unknown_tools():
    registry = ToolRegistry((EchoTool(),))

    with pytest.raises(ValueError, match="already registered"):
        registry.register(EchoTool())
    with pytest.raises(UnknownAgentToolError, match="unknown agent tool"):
        registry.describe(("missing",))


@pytest.mark.asyncio
async def test_registry_separates_registration_from_agent_authorization():
    registry = ToolRegistry((EchoTool(),))

    with pytest.raises(AgentToolNotAllowedError, match="not allowed"):
        await registry.execute(
            "echo",
            {"text": "blocked"},
            allowed_tools=(),
        )


@pytest.mark.asyncio
async def test_registry_injects_context_outside_model_arguments():
    tool = EchoTool()
    registry = ToolRegistry((tool,))
    context = AgentToolExecutionContext(
        session_id="session-1",
        episode_id="episode-1",
    )

    result = await registry.execute(
        "echo",
        {"text": "hello"},
        allowed_tools=("echo",),
        context=context,
    )

    assert result == {"text": "hello"}
    assert tool.calls == [{"text": "hello", "context": context}]
