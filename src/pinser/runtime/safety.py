"""Shared filesystem and path safety primitives for Phase 2."""

from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path

_BLOCKED_READ_PATHS = {
    "/dev/console",
    "/dev/fd/0",
    "/dev/fd/1",
    "/dev/fd/2",
    "/dev/full",
    "/dev/random",
    "/dev/stderr",
    "/dev/stdin",
    "/dev/stdout",
    "/dev/tty",
    "/dev/urandom",
    "/dev/zero",
}
_BLOCKED_WRITE_PATHS = {
    ".pinser",
    ".git",
}


@dataclass(frozen=True, slots=True)
class PathSafetyDecision:
    """Normalized outcome for a filesystem safety check."""

    allowed: bool
    reason: str | None = None
    requires_approval: bool = False


@dataclass(frozen=True, slots=True)
class ResolvedPath:
    """Workspace-relative path details used by tool safety checks."""

    original: str
    expanded: Path
    comparison_path: str
    workspace_relative: str | None


class PathSafety:
    """Shared path normalization and guard checks for local tools."""

    def __init__(self, workspace_root: Path) -> None:
        self._workspace_root = workspace_root.expanduser().resolve()

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    def resolve(self, raw_path: str) -> ResolvedPath:
        expanded = self._expand_path(raw_path)
        comparison_path = self._comparison_path(expanded)
        workspace_relative = self._workspace_relative(expanded)
        return ResolvedPath(
            original=raw_path,
            expanded=expanded,
            comparison_path=comparison_path,
            workspace_relative=workspace_relative,
        )

    def check_read_path(self, raw_path: str) -> PathSafetyDecision:
        if self._looks_like_network_path(raw_path):
            return PathSafetyDecision(
                allowed=False,
                reason="network-path-requires-approval",
                requires_approval=True,
            )

        resolved = self.resolve(raw_path)
        if resolved.comparison_path in _BLOCKED_READ_PATHS:
            return PathSafetyDecision(allowed=False, reason="blocked-special-file")
        if resolved.workspace_relative is None:
            return PathSafetyDecision(allowed=False, reason="path-outside-workspace")
        return PathSafetyDecision(allowed=True)

    def check_write_path(self, raw_path: str) -> PathSafetyDecision:
        if self._looks_like_network_path(raw_path):
            return PathSafetyDecision(
                allowed=False,
                reason="network-path-requires-approval",
                requires_approval=True,
            )

        resolved = self.resolve(raw_path)
        if resolved.workspace_relative is None:
            return PathSafetyDecision(allowed=False, reason="path-outside-workspace")

        top_level = resolved.workspace_relative.split("/", maxsplit=1)[0].lower()
        if top_level in _BLOCKED_WRITE_PATHS:
            return PathSafetyDecision(allowed=False, reason="protected-path")
        return PathSafetyDecision(allowed=True)

    def require_regular_file_read(self, raw_path: str) -> ResolvedPath:
        decision = self.check_read_path(raw_path)
        if not decision.allowed:
            msg = f"file not found: {raw_path}"
            raise FileNotFoundError(msg)
        resolved = self.resolve(raw_path)
        self._require_existing_regular_file(resolved)
        return resolved

    def require_regular_file_write_target(self, raw_path: str) -> ResolvedPath:
        decision = self.check_write_path(raw_path)
        if not decision.allowed:
            msg = f"file not found: {raw_path}"
            raise FileNotFoundError(msg)
        resolved = self.resolve(raw_path)
        if resolved.expanded.exists():
            self._require_existing_regular_file(resolved)
        return resolved

    def _workspace_relative(self, path: Path) -> str | None:
        try:
            relative = path.relative_to(self._workspace_root)
        except ValueError:
            return None
        return relative.as_posix() or "."

    @staticmethod
    def _comparison_path(path: Path) -> str:
        return path.as_posix().lower()

    @staticmethod
    def _looks_like_network_path(raw_path: str) -> bool:
        return raw_path.startswith("//") or raw_path.startswith("\\\\")

    def _expand_path(self, raw_path: str) -> Path:
        expanded = Path(raw_path).expanduser()
        if expanded.is_absolute():
            return expanded.resolve(strict=False)
        return (self._workspace_root / expanded).resolve(strict=False)

    @staticmethod
    def _is_regular_file(path: Path) -> bool:
        try:
            mode = path.stat().st_mode
        except OSError:
            return False
        return stat.S_ISREG(mode)

    def _require_existing_regular_file(self, resolved: ResolvedPath) -> None:
        if not resolved.expanded.exists():
            msg = f"file not found: {resolved.original}"
            raise FileNotFoundError(msg)
        if not self._is_regular_file(resolved.expanded):
            msg = f"path is not a regular file: {resolved.original}"
            raise IsADirectoryError(msg)
