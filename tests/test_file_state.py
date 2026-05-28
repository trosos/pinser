from pathlib import Path

import pytest

from pinser.runtime.engine.file_state import FileStateTracker
from pinser.runtime.tools_errors import ToolSafetyBlockedError


def test_file_state_tracker_requires_prior_read_for_overwrite(tmp_path: Path) -> None:
    tracker = FileStateTracker(workspace_root=tmp_path)

    with pytest.raises(ToolSafetyBlockedError, match="requires prior read"):
        tracker.require_safe_overwrite("note.txt", "current")


def test_file_state_tracker_rejects_partial_prior_read(tmp_path: Path) -> None:
    tracker = FileStateTracker(workspace_root=tmp_path)
    tracker.record_read("note.txt", "current", is_partial=True)

    with pytest.raises(ToolSafetyBlockedError, match="requires non-partial prior read"):
        tracker.require_safe_overwrite("note.txt", "current")


def test_file_state_tracker_rejects_stale_overwrite(tmp_path: Path) -> None:
    tracker = FileStateTracker(workspace_root=tmp_path)
    tracker.record_read("note.txt", "old")

    with pytest.raises(ToolSafetyBlockedError, match="file changed since last read"):
        tracker.require_safe_overwrite("note.txt", "new")


def test_file_state_tracker_records_write_as_fresh_observation(tmp_path: Path) -> None:
    tracker = FileStateTracker(workspace_root=tmp_path)
    tracker.record_write("note.txt", "written")

    tracker.require_safe_overwrite("note.txt", "written")
