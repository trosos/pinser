"""Tool protocol definitions for Phase 2 runtime scaffolding."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from pinser.runtime.permissions import PermissionDecision, PermissionRequest


@dataclass(frozen=True, slots=True)
class ToolInvocation:
    """Validated tool invocation as seen by the runtime."""

    tool_name: str
    arguments: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ToolExecutionResult:
    """Tool execution result returned to the runtime."""

    summary: str
    output: Mapping[str, Any]


class Tool(Protocol):
    """Minimal Phase 2 tool contract."""

    @property
    def name(self) -> str: ...

    def build_permission_request(self, invocation: ToolInvocation) -> PermissionRequest: ...

    def decide_permission(self, invocation: ToolInvocation) -> PermissionDecision: ...

    async def execute(self, invocation: ToolInvocation) -> ToolExecutionResult: ...
