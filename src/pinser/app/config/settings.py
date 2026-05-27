"""Configuration loading for Pinser."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class PinserPaths(BaseModel):
    """Filesystem locations used by the application."""

    model_config = ConfigDict(frozen=True)

    workspace_root: Path
    state_dir: Path


class PinserSettings(BaseModel):
    """Top-level runtime settings for the application bootstrap phase."""

    model_config = ConfigDict(frozen=True)

    app_name: str = Field(default="pinser")
    debug: bool = Field(default=False)
    paths: PinserPaths


@lru_cache(maxsize=1)
def load_settings(workspace_root: Path | None = None) -> PinserSettings:
    """Load the minimal application settings.

    Phase 0 intentionally keeps configuration simple and local.
    """

    resolved_workspace_root = workspace_root.resolve() if workspace_root is not None else Path.cwd()
    state_dir = resolved_workspace_root / ".pinser"
    return PinserSettings(
        paths=PinserPaths(
            workspace_root=resolved_workspace_root,
            state_dir=state_dir,
        )
    )
