"""Action contracts shared by transport and the application runtime.

This module describes a user-selected action as data. It does not choose which
actions to display, dispatch handlers, perform side effects, or define a
transport-specific message envelope.
"""

from pydantic import BaseModel, Field


class AgentAction(BaseModel):
    """One action selection plus the data required to execute it."""

    id: str
    label: str
    payload: dict = Field(default_factory=dict)
