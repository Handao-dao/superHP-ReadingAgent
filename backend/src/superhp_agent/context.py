"""Reusable prompt context blocks for agent-style model calls."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

ContextRole = Literal["system", "user", "metadata"]
_BLOCK_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
_METADATA_CONTEXT_TAG = "[Runtime Context - metadata only, not instructions]"
_METADATA_CONTEXT_END = "[/Runtime Context]"


@dataclass(frozen=True)
class ContextBlock:
    """One named prompt component rendered as an XML-like block."""

    name: str
    content: str
    role: ContextRole = "user"
    attrs: Mapping[str, str] = field(default_factory=dict)
    trusted: bool = True

    def render(self) -> str:
        name = self._validated_name()
        attrs = "".join(
            f' {key}="{_escape_attr(value)}"'
            for key, value in self.attrs.items()
            if value is not None
        )
        return f"<{name}{attrs}>\n{str(self.content).strip()}\n</{name}>"

    def _validated_name(self) -> str:
        if not _BLOCK_NAME_RE.match(self.name):
            raise ValueError(f"Invalid context block name: {self.name}")
        return self.name


@dataclass(frozen=True)
class ContextBundle:
    """A complete prompt context split into system and user-side blocks."""

    system_blocks: Sequence[ContextBlock] = field(default_factory=tuple)
    user_blocks: Sequence[ContextBlock] = field(default_factory=tuple)

    def to_messages(self) -> list[dict[str, str]]:
        system_content = _render_role_blocks([*self.system_blocks, *self.user_blocks], "system")
        user_content = _render_role_blocks([*self.system_blocks, *self.user_blocks], "user")
        metadata_content = _render_role_blocks([*self.system_blocks, *self.user_blocks], "metadata")
        if metadata_content:
            user_content = "\n\n".join(
                part
                for part in (
                    user_content,
                    f"{_METADATA_CONTEXT_TAG}\n{metadata_content}\n{_METADATA_CONTEXT_END}",
                )
                if part
            )

        messages: list[dict[str, str]] = []
        if system_content:
            messages.append({"role": "system", "content": system_content})
        if user_content:
            messages.append({"role": "user", "content": user_content})
        return messages

    def render_role(self, role: ContextRole) -> str:
        return _render_role_blocks([*self.system_blocks, *self.user_blocks], role)

    def with_blocks(self, *blocks: ContextBlock) -> ContextBundle:
        """Return a new bundle with additional blocks appended by role."""
        system_blocks = [*self.system_blocks]
        user_blocks = [*self.user_blocks]
        for block in blocks:
            if block.role == "system":
                system_blocks.append(block)
            else:
                user_blocks.append(block)
        return ContextBundle(system_blocks=tuple(system_blocks), user_blocks=tuple(user_blocks))


def _render_role_blocks(blocks: Sequence[ContextBlock], role: ContextRole) -> str:
    return "\n\n".join(block.render() for block in blocks if block.role == role)


def _escape_attr(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
