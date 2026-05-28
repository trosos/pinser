"""Workspace-scoped exact-text replacement edit tool for Phase 2 runtime."""

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
class EditTool:
    """Replace an exact text snippet in a workspace file."""

    workspace_root: Path
    file_state: FileStateTracker | None = None
    name: str = "Edit"

    def build_permission_request(self, invocation: ToolInvocation) -> PermissionRequest:
        path = self._require_path(invocation)
        return PermissionRequest(
            tool_name=self.name,
            summary=f"edit {path}",
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
        old_string = self._require_string_argument(invocation, "old_string")
        new_string = self._require_string_argument(invocation, "new_string")
        replace_all = self._require_replace_all(invocation)

        safety = PathSafety(self.workspace_root)
        resolved = safety.resolve(path)
        target = resolved.expanded
        if target.suffix == ".ipynb":
            msg = "notebook files must be edited with the notebook-specific tool"
            raise ValueError(msg)

        original_content = target.read_text()
        if self.file_state is not None:
            try:
                self.file_state.require_safe_overwrite(path, original_content)
            except ValueError as exc:
                if str(exc) == "write requires prior read for existing file":
                    raise ValueError("edit requires prior read for existing file") from exc
                raise

        occurrences = original_content.count(old_string)
        if occurrences == 0:
            msg = "old_string not found in file"
            raise ValueError(msg)
        if not replace_all and occurrences != 1:
            msg = "old_string must match exactly once; use replace_all for multiple matches"
            raise ValueError(msg)

        updated_content = original_content.replace(
            old_string,
            new_string,
            -1 if replace_all else 1,
        )
        target.write_text(updated_content)
        if self.file_state is not None:
            self.file_state.record_write(path, updated_content)

        display_path = resolved.workspace_relative or resolved.expanded.as_posix()
        replacement_count = occurrences if replace_all else 1
        return ToolExecutionResult(
            summary=f"edited {display_path}",
            output={
                "type": "update",
                "path": display_path,
                "original_content": original_content,
                "content": updated_content,
                "replacements": replacement_count,
                "diff": self._build_diff(display_path, original_content, updated_content),
            },
        )

    @staticmethod
    def _require_path(invocation: ToolInvocation) -> str:
        path = invocation.arguments.get("path")
        if not isinstance(path, str) or not path:
            msg = "Edit tool requires a non-empty string path argument."
            raise ValueError(msg)
        return path

    @staticmethod
    def _require_string_argument(invocation: ToolInvocation, key: str) -> str:
        value = invocation.arguments.get(key)
        if not isinstance(value, str):
            msg = f"Edit tool requires a string {key} argument."
            raise ValueError(msg)
        return value

    @staticmethod
    def _require_replace_all(invocation: ToolInvocation) -> bool:
        value = invocation.arguments.get("replace_all", False)
        if not isinstance(value, bool):
            msg = "Edit tool requires replace_all to be a boolean when provided."
            raise ValueError(msg)
        return value

    @staticmethod
    def _build_diff(
        display_path: str, original_content: str, updated_content: str
    ) -> list[str]:
        return list(
            unified_diff(
                original_content.splitlines(),
                updated_content.splitlines(),
                fromfile=f"a/{display_path}",
                tofile=f"b/{display_path}",
                lineterm="",
            )
        )
