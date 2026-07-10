"""Capability interfaces used by backend application and service layers."""

from superhp_agent.ports.events import EventEmitter, EventSink, emit_backend_event

__all__ = ["EventEmitter", "EventSink", "emit_backend_event"]
