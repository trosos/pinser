"""Workspace-scoped whole-file write tool for Phase 2 runtime."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import unified_diff
from pathlib import Path

from pinser.runtime.engine.file_state import FileStateTracker
from pinser.runtime.permissions import (
    PermissionDecision,
    PermissionDecisionKind,
    PermissionRequest,
)
from pinser.runtime.safety import PathSafety
from pinser.runtime.tools.protocol import ToolExecutionResult, ToolInvocation


@dataclass(frozen=True, slots=True)
class WriteTool:
    """Create or replace a workspace file with exact caller-provided content."""

    workspace_root: Path
    file_state: FileStateTracker | None = None
    name: str = "Write"

    def build_permission_request(self, invocation: ToolInvocation) -> PermissionRequest:
        path = self._require_path(invocation)
        return PermissionRequest(
            tool_name=self.name,
            summary=f"write {path}",
            resource=path,
        )

    def decide_permission(self, invocation: ToolInvocation) -> PermissionDecision:
        path = self._require_path(invocation)
        safety = PathSafety(self.workspace_root)
        decision = safety.check_write_path(path)
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
        content = self._require_content(invocation)
        safety = PathSafety(self.workspace_root)
        resolved = safety.resolve(path)
        target = resolved.expanded
        original_content = target.read_text() if target.exists() else None
        if original_content is not None and self.file_state is not None:
            self.file_state.require_safe_overwrite(path, original_content)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        if self.file_state is not None:
            self.file_state.record_write(path, content)
        write_type = "update" if original_content is not None else "create"
        display_path = resolved.workspace_relative or resolved.expanded.as_posix()
        return ToolExecutionResult(
            summary=f"{write_type}d {display_path}",
            output={
                "type": write_type,
                "path": display_path,
                "content": content,
                "original_content": original_content,
                "diff": self._build_diff(display_path, original_content, content),
            },
        )

    @staticmethod
    def _require_path(invocation: ToolInvocation) -> str:
        path = invocation.arguments.get("path")
        if not isinstance(path, str) or not path:
            msg = "Write tool requires a non-empty string path argument."
            raise ValueError(msg)
        return path

    @staticmethod
    def _require_content(invocation: ToolInvocation) -> str:
        content = invocation.arguments.get("content")
        if not isinstance(content, str):
            msg = "Write tool requires a string content argument."
            raise ValueError(msg)
        return content

    @staticmethod
    def _build_diff(
        display_path: str, original_content: str | None, new_content: str
    ) -> list[str]:
        before_lines = [] if original_content is None else original_content.splitlines()
        after_lines = new_content.splitlines()
        return list(
            unified_diff(
                before_lines,
                after_lines,
                fromfile=f"a/{display_path}",
                tofile=f"b/{display_path}",
                lineterm="",
            )
        )
