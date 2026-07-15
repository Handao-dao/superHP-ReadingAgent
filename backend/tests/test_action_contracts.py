"""Tests for the action contract shared across application boundaries."""

from superhp_agent.contracts import AgentAction


def test_agent_action_keeps_json_shape():
    action = AgentAction(id="open_chapter", label="Open", payload={"unit_id": "hp01-ch01"})

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
