"""Compatibility tests for the first extracted application contract."""

from superhp_agent.contracts import AgentAction
from superhp_agent.schemas import AgentAction as LegacyAgentAction


def test_agent_action_keeps_legacy_import_and_json_shape():
    action = AgentAction(id="open_chapter", label="Open", payload={"unit_id": "hp01-ch01"})

    assert LegacyAgentAction is AgentAction
    assert action.model_dump() == {
        "id": "open_chapter",
        "label": "Open",
        "payload": {"unit_id": "hp01-ch01"},
    }


def test_agent_action_payload_default_is_not_shared():
    first = AgentAction(id="read_original", label="Original")
    second = AgentAction(id="read_original", label="Original")

    first.payload["unit_id"] = "hp01-ch01"

    assert second.payload == {}
