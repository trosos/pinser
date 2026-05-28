"""Write-tracking primitives for read-before-write and stale-read safety."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pinser.runtime.safety import PathSafety


@dataclass(frozen=True, slots=True)
class FileObservation:
    """Known file state captured from a successful read or write."""

    path: str
    content: str
    is_partial: bool = False


@dataclass(slots=True)
class FileStateTracker:
    """Session-local knowledge used to enforce write safety invariants."""

    workspace_root: Path
    _observations: dict[str, FileObservation] = field(default_factory=dict)

    def record_read(self, path: str, content: str, *, is_partial: bool = False) -> None:
        resolved_path = self._resolve_workspace_path(path)
        self._observations[resolved_path] = FileObservation(
            path=resolved_path,
            content=content,
            is_partial=is_partial,
        )

    def record_write(self, path: str, content: str) -> None:
        resolved_path = self._resolve_workspace_path(path)
        self._observations[resolved_path] = FileObservation(
            path=resolved_path,
            content=content,
            is_partial=False,
        )

    def require_safe_overwrite(self, path: str, current_content: str) -> None:
        resolved_path = self._resolve_workspace_path(path)
        observation = self._observations.get(resolved_path)
        if observation is None:
            msg = "write requires prior read for existing file"
            raise ValueError(msg)
        if observation.is_partial:
            msg = "write requires non-partial prior read for existing file"
            raise ValueError(msg)
        if observation.content != current_content:
            msg = "write blocked because file changed since last read"
            raise ValueError(msg)

    def _resolve_workspace_path(self, path: str) -> str:
        safety = PathSafety(self.workspace_root)
        resolved = safety.resolve(path)
        return resolved.workspace_relative or resolved.expanded.as_posix()
