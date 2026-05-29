from pathlib import Path

import pytest

from pinser.runtime import PathSafety
from pinser.runtime.engine.file_state import FileStateTracker
from pinser.runtime.tools import EditTool, ReadTool, WriteTool
from pinser.runtime.tools.protocol import ToolInvocation
from pinser.runtime.tools_errors import ToolSafetyBlockedError


def test_path_safety_resolves_relative_paths_inside_workspace(tmp_path: Path) -> None:
    safety = PathSafety(tmp_path)

    resolved = safety.resolve("src/main.py")

    assert resolved.expanded == tmp_path / "src/main.py"
    assert resolved.workspace_relative == "src/main.py"
    assert resolved.comparison_path.endswith("/src/main.py")


def test_path_safety_blocks_paths_outside_workspace(tmp_path: Path) -> None:
    safety = PathSafety(tmp_path)

    decision = safety.check_read_path("../secret.txt")

    assert not decision.allowed
    assert decision.reason == "path-outside-workspace"
    assert not decision.requires_approval


def test_path_safety_marks_network_like_paths_as_manual_approval(tmp_path: Path) -> None:
    safety = PathSafety(tmp_path)

    decision = safety.check_read_path("//server/share/file.txt")

    assert not decision.allowed
    assert decision.reason == "network-path-requires-approval"
    assert decision.requires_approval


def test_path_safety_blocks_known_special_read_paths(tmp_path: Path) -> None:
    safety = PathSafety(tmp_path)

    decision = safety.check_read_path("/dev/zero")

    assert not decision.allowed
    assert decision.reason == "blocked-special-file"


@pytest.mark.asyncio
async def test_read_tool_rejects_directory_targets(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    tool = ReadTool(workspace_root=tmp_path)

    with pytest.raises(IsADirectoryError, match="not a regular file"):
        await tool.execute(ToolInvocation(tool_name="Read", arguments={"path": "docs"}))


@pytest.mark.asyncio
async def test_write_tool_rejects_directory_targets(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    tool = WriteTool(workspace_root=tmp_path)

    with pytest.raises(IsADirectoryError, match="not a regular file"):
        await tool.execute(
            ToolInvocation(
                tool_name="Write",
                arguments={"path": "docs", "content": "hello"},
            )
        )


@pytest.mark.asyncio
async def test_edit_tool_rejects_directory_targets(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    tool = EditTool(workspace_root=tmp_path)

    with pytest.raises(IsADirectoryError, match="not a regular file"):
        await tool.execute(
            ToolInvocation(
                tool_name="Edit",
                arguments={"path": "docs", "old_string": "a", "new_string": "b"},
            )
        )


def test_path_safety_blocks_symlink_escape_from_workspace(tmp_path: Path) -> None:
    outside_dir = tmp_path.parent / "outside"
    outside_dir.mkdir(exist_ok=True)
    outside_file = outside_dir / "secret.txt"
    outside_file.write_text("secret")
    (tmp_path / "escaped-link.txt").symlink_to(outside_file)

    safety = PathSafety(tmp_path)

    decision = safety.check_read_path("escaped-link.txt")

    assert not decision.allowed
    assert decision.reason == "path-outside-workspace"


def test_path_safety_treats_dotdot_that_resolves_inside_workspace_as_allowed(
    tmp_path: Path,
) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    target = tmp_path / "note.txt"
    target.write_text("hello")
    safety = PathSafety(tmp_path)

    decision = safety.check_read_path("nested/../note.txt")

    assert decision.allowed
    resolved = safety.resolve("nested/../note.txt")
    assert resolved.workspace_relative == "note.txt"


def test_path_safety_blocks_case_insensitive_protected_write_paths(tmp_path: Path) -> None:
    safety = PathSafety(tmp_path)

    decision = safety.check_write_path(".PINSER/settings.json")

    assert not decision.allowed
    assert decision.reason == "protected-path"


@pytest.mark.asyncio
async def test_read_tool_rejects_symlink_that_resolves_outside_workspace(
    tmp_path: Path,
) -> None:
    outside_dir = tmp_path.parent / "outside-read"
    outside_dir.mkdir(exist_ok=True)
    outside_file = outside_dir / "secret.txt"
    outside_file.write_text("secret")
    (tmp_path / "note.txt").symlink_to(outside_file)
    tool = ReadTool(workspace_root=tmp_path)

    with pytest.raises(FileNotFoundError, match="file not found"):
        await tool.execute(ToolInvocation(tool_name="Read", arguments={"path": "note.txt"}))


@pytest.mark.asyncio
async def test_write_tool_rejects_symlink_target_that_resolves_outside_workspace(
    tmp_path: Path,
) -> None:
    outside_dir = tmp_path.parent / "outside-write"
    outside_dir.mkdir(exist_ok=True)
    outside_file = outside_dir / "secret.txt"
    outside_file.write_text("secret")
    (tmp_path / "note.txt").symlink_to(outside_file)
    tracker = FileStateTracker(workspace_root=tmp_path)
    tracker.record_read("note.txt", "secret")
    tool = WriteTool(workspace_root=tmp_path, file_state=tracker)

    with pytest.raises(FileNotFoundError, match="file not found"):
        await tool.execute(
            ToolInvocation(
                tool_name="Write",
                arguments={"path": "note.txt", "content": "changed"},
            )
        )


@pytest.mark.asyncio
async def test_edit_tool_blocks_partial_read_observations(tmp_path: Path) -> None:
    file_path = tmp_path / "note.txt"
    file_path.write_text("alpha\nbeta\n")
    tracker = FileStateTracker(workspace_root=tmp_path)
    tracker.record_read("note.txt", "alpha\n", is_partial=True)
    tool = EditTool(workspace_root=tmp_path, file_state=tracker)

    with pytest.raises(
        ToolSafetyBlockedError,
        match="write requires non-partial prior read for existing file",
    ):
        await tool.execute(
            ToolInvocation(
                tool_name="Edit",
                arguments={
                    "path": "note.txt",
                    "old_string": "beta",
                    "new_string": "gamma",
                },
            )
        )
