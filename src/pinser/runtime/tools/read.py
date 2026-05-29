"""Read-only file tool for the first Phase 2 runtime slice."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pinser.runtime.engine.file_state import FileStateTracker
from pinser.runtime.permissions import (
    PermissionDecision,
    PermissionDecisionKind,
    PermissionRequest,
)
from pinser.runtime.safety import PathSafety
from pinser.runtime.tools.protocol import ToolExecutionResult, ToolInvocation
from pinser.runtime.tools_errors import ToolArgumentError


@dataclass(frozen=True, slots=True)
class ReadTool:
    """Minimal read-only file tool backed by shared path safety checks."""

    workspace_root: Path
    file_state: FileStateTracker | None = None
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
        resolved = safety.require_regular_file_read(path)
        content = resolved.expanded.read_text()
        display_path = resolved.workspace_relative or resolved.expanded.as_posix()
        if self.file_state is not None:
            self.file_state.record_read(display_path, content)
        return ToolExecutionResult(
            summary=f"read {display_path}",
            output={
                "path": display_path,
                "content": content,
            },
        )

    @staticmethod
    def _require_path(invocation: ToolInvocation) -> str:
        path = invocation.arguments.get("path")
        if not isinstance(path, str) or not path:
            msg = "Read tool requires a non-empty string path argument."
            raise ToolArgumentError(msg)
        return path
