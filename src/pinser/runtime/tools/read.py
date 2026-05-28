"""Read-only file tool for the first Phase 2 runtime slice."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pinser.runtime.permissions import (
    PermissionDecision,
    PermissionDecisionKind,
    PermissionRequest,
)
from pinser.runtime.safety import PathSafety
from pinser.runtime.tools.protocol import ToolExecutionResult, ToolInvocation


@dataclass(frozen=True, slots=True)
class ReadTool:
    """Minimal read-only file tool backed by shared path safety checks."""

    workspace_root: Path
    name: str = "Read"

    def build_permission_request(self, invocation: ToolInvocation) -> PermissionRequest:
        path = self._require_path(invocation)
        return PermissionRequest(
            tool_name=self.name,
            summary=f"read {path}",
            resource=path,
        )

    def decide_permission(self, invocation: ToolInvocation) -> PermissionDecision:
        path = self._require_path(invocation)
        safety = PathSafety(self.workspace_root)
        decision = safety.check_read_path(path)
        if decision.allowed:
            return PermissionDecision(kind=PermissionDecisionKind.ALLOW)
        if decision.requires_approval:
            return PermissionDecision(
                kind=PermissionDecisionKind.ASK,
                reason=decision.reason,
            )
        return PermissionDecision(
            kind=PermissionDecisionKind.DENY,
            reason=decision.reason,
        )

    async def execute(self, invocation: ToolInvocation) -> ToolExecutionResult:
        path = self._require_path(invocation)
        safety = PathSafety(self.workspace_root)
        resolved = safety.resolve(path)
        content = resolved.expanded.read_text()
        return ToolExecutionResult(
            summary=f"read {resolved.workspace_relative or resolved.expanded.as_posix()}",
            output={
                "path": resolved.workspace_relative or resolved.expanded.as_posix(),
                "content": content,
            },
        )

    @staticmethod
    def _require_path(invocation: ToolInvocation) -> str:
        path = invocation.arguments.get("path")
        if not isinstance(path, str) or not path:
            msg = "Read tool requires a non-empty string path argument."
            raise ValueError(msg)
        return path
