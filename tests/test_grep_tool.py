from pathlib import Path

import pytest

from pinser.runtime.tools import GrepTool
from pinser.runtime.tools.protocol import ToolInvocation


@pytest.mark.asyncio
async def test_grep_tool_returns_workspace_relative_matches_with_line_info(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.txt").write_text("alpha\nTODO one\nomega\n")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "b.txt").write_text("TODO two\nnope\n")
    (tmp_path / "note.md").write_text("TODO ignored by glob\n")

    tool = GrepTool(workspace_root=tmp_path)

    result = await tool.execute(
        ToolInvocation(tool_name="Grep", arguments={"pattern": "TODO", "glob": "**/*.txt"})
    )

    assert result.summary == "matched 2 line(s)"
    assert result.output == {
        "pattern": "TODO",
        "glob": "**/*.txt",
        "matches": [
            {"path": "a.txt", "line_number": 2, "line": "TODO one"},
            {"path": "nested/b.txt", "line_number": 1, "line": "TODO two"},
        ],
    }


def test_grep_tool_requires_non_empty_pattern(tmp_path: Path) -> None:
    tool = GrepTool(workspace_root=tmp_path)

    with pytest.raises(ValueError, match="non-empty string pattern"):
        tool.build_permission_request(ToolInvocation(tool_name="Grep", arguments={}))


@pytest.mark.asyncio
async def test_grep_tool_rejects_empty_glob_when_provided(tmp_path: Path) -> None:
    tool = GrepTool(workspace_root=tmp_path)

    with pytest.raises(ValueError, match="glob argument must be a non-empty string"):
        await tool.execute(
            ToolInvocation(tool_name="Grep", arguments={"pattern": "TODO", "glob": ""})
        )
