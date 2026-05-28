"""Workspace-scoped grep tool for Phase 2 runtime."""

from __future__ import annotations

import re
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
class GrepTool:
    """Search workspace file contents for a regex pattern."""

    workspace_root: Path
    name: str = "Grep"

    def build_permission_request(self, invocation: ToolInvocation) -> PermissionRequest:
        pattern = self._require_pattern(invocation)
        return PermissionRequest(
            tool_name=self.name,
            summary=f"grep {pattern}",
            resource=pattern,
        )

    def decide_permission(self, invocation: ToolInvocation) -> PermissionDecision:
        return PermissionDecision(kind=PermissionDecisionKind.ALLOW)

    async def execute(self, invocation: ToolInvocation) -> ToolExecutionResult:
        pattern = self._require_pattern(invocation)
        regex = re.compile(pattern)
        glob = self._optional_glob(invocation)
        matches = self._collect_matches(regex, glob)
        return ToolExecutionResult(
            summary=f"matched {len(matches)} line(s)",
            output={
                "pattern": pattern,
                "glob": glob,
                "matches": matches,
            },
        )

    def _collect_matches(
        self, regex: re.Pattern[str], glob: str | None
    ) -> list[dict[str, str | int]]:
        safety = PathSafety(self.workspace_root)
        candidates = (
            self.workspace_root.rglob("*")
            if glob is None
            else self.workspace_root.glob(glob)
        )
        matches: list[dict[str, str | int]] = []
        for candidate in sorted(candidates):
            if not candidate.is_file():
                continue
            try:
                resolved = candidate.resolve(strict=False)
            except OSError:
                continue
            workspace_relative = safety.resolve(resolved.as_posix()).workspace_relative
            if workspace_relative is None:
                continue
            try:
                lines = resolved.read_text().splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for line_number, line in enumerate(lines, start=1):
                if regex.search(line) is None:
                    continue
                matches.append(
                    {
                        "path": workspace_relative,
                        "line_number": line_number,
                        "line": line,
                    }
                )
        return matches

    @staticmethod
    def _require_pattern(invocation: ToolInvocation) -> str:
        pattern = invocation.arguments.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            msg = "Grep tool requires a non-empty string pattern argument."
            raise ValueError(msg)
        return pattern

    @staticmethod
    def _optional_glob(invocation: ToolInvocation) -> str | None:
        glob = invocation.arguments.get("glob")
        if glob is None:
            return None
        if not isinstance(glob, str) or not glob:
            msg = "Grep tool glob argument must be a non-empty string when provided."
            raise ValueError(msg)
        return glob
