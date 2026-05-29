"""Workspace-scoped glob tool for Phase 2 runtime."""

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
from pinser.runtime.tools_errors import ToolArgumentError


@dataclass(frozen=True, slots=True)
class GlobTool:
    """List files under the workspace matching a glob pattern."""

    workspace_root: Path
    name: str = "Glob"

    def build_permission_request(self, invocation: ToolInvocation) -> PermissionRequest:
        pattern = self._require_pattern(invocation)
        return PermissionRequest(
            tool_name=self.name,
            summary=f"glob {pattern}",
            resource=pattern,
        )

    def decide_permission(self, invocation: ToolInvocation) -> PermissionDecision:
        return PermissionDecision(kind=PermissionDecisionKind.ALLOW)

    async def execute(self, invocation: ToolInvocation) -> ToolExecutionResult:
        pattern = self._require_pattern(invocation)
        matches = self._collect_matches(pattern)
        return ToolExecutionResult(
            summary=f"matched {len(matches)} path(s)",
            output={
                "pattern": pattern,
                "matches": matches,
            },
        )

    def _collect_matches(self, pattern: str) -> list[str]:
        safety = PathSafety(self.workspace_root)
        matches: list[str] = []
        for candidate in self.workspace_root.glob(pattern):
            try:
                resolved = candidate.resolve(strict=False)
            except OSError:
                continue
            workspace_relative = safety.resolve(resolved.as_posix()).workspace_relative
            if workspace_relative is None:
                continue
            matches.append(workspace_relative)
        return sorted(set(matches))

    @staticmethod
    def _require_pattern(invocation: ToolInvocation) -> str:
        pattern = invocation.arguments.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            msg = "Glob tool requires a non-empty string pattern argument."
            raise ToolArgumentError(msg)
        return pattern
