"""Capability interfaces used by backend application and service layers."""

from superhp_agent.ports.events import EventEmitter, EventSink, emit_backend_event
from superhp_agent.ports.llm import LLMProvider

__all__ = ["EventEmitter", "EventSink", "LLMProvider", "emit_backend_event"]
