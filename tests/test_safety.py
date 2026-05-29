from pathlib import Path

import pytest

from pinser.runtime import PathSafety
from pinser.runtime.tools import EditTool, ReadTool, WriteTool
from pinser.runtime.tools.protocol import ToolInvocation


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
