from pathlib import Path

import pytest

from pinser.runtime.tools import GlobTool, ToolArgumentError
from pinser.runtime.tools.glob import MAX_GLOB_MATCHES
from pinser.runtime.tools.protocol import ToolInvocation


@pytest.mark.asyncio
async def test_glob_tool_returns_workspace_relative_matches(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "b.txt").write_text("b")
    (tmp_path / "note.md").write_text("c")

    tool = GlobTool(workspace_root=tmp_path)

    result = await tool.execute(ToolInvocation(tool_name="Glob", arguments={"pattern": "**/*.txt"}))

    assert result.summary == "matched 2 path(s)"
    assert result.output == {
        "pattern": "**/*.txt",
        "matches": ["a.txt", "nested/b.txt"],
        "truncated": False,
        "total_matches": 2,
    }


def test_glob_tool_requires_non_empty_pattern(tmp_path: Path) -> None:
    tool = GlobTool(workspace_root=tmp_path)

    with pytest.raises(ToolArgumentError, match="non-empty string pattern"):
        tool.build_permission_request(ToolInvocation(tool_name="Glob", arguments={}))


@pytest.mark.asyncio
async def test_glob_tool_truncates_matches_to_budget(tmp_path: Path) -> None:
    for index in range(MAX_GLOB_MATCHES + 10):
        (tmp_path / f"file-{index:02d}.txt").write_text(str(index))

    tool = GlobTool(workspace_root=tmp_path)

    result = await tool.execute(ToolInvocation(tool_name="Glob", arguments={"pattern": "*.txt"}))

    assert len(result.output["matches"]) == MAX_GLOB_MATCHES
    assert result.output["truncated"] is True
    assert result.output["total_matches"] == MAX_GLOB_MATCHES + 10
    assert result.summary == (
        f"matched {MAX_GLOB_MATCHES + 10} path(s), returning first {MAX_GLOB_MATCHES}"
    )
