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

MAX_GLOB_MATCHES = 50


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
        matches, total_matches = self._collect_matches(pattern)
        truncated = total_matches > len(matches)
        summary = f"matched {total_matches} path(s)"
        if truncated:
            summary = f"matched {total_matches} path(s), returning first {len(matches)}"
        return ToolExecutionResult(
            summary=summary,
            output={
                "pattern": pattern,
                "matches": matches,
                "truncated": truncated,
                "total_matches": total_matches,
            },
        )

    def _collect_matches(self, pattern: str) -> tuple[list[str], int]:
        safety = PathSafety(self.workspace_root)
        unique_matches: set[str] = set()
        for candidate in self.workspace_root.glob(pattern):
            try:
                resolved = candidate.resolve(strict=False)
            except OSError:
                continue
            workspace_relative = safety.resolve(resolved.as_posix()).workspace_relative
            if workspace_relative is None:
                continue
            unique_matches.add(workspace_relative)
        sorted_matches = sorted(unique_matches)
        return sorted_matches[:MAX_GLOB_MATCHES], len(sorted_matches)

    @staticmethod
    def _require_pattern(invocation: ToolInvocation) -> str:
        pattern = invocation.arguments.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            msg = "Glob tool requires a non-empty string pattern argument."
            raise ToolArgumentError(msg)
        return pattern
