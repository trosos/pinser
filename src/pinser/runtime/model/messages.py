"""Structured assistant outputs used by the local runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ToolCall:
    """Model-requested tool invocation for the local runtime."""

    tool_name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AssistantStep:
    """Assistant step containing optional user-visible text and tool request."""

    message: str | None = None
    tool_call: ToolCall | None = None
