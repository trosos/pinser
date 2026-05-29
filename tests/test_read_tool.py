from pathlib import Path

import pytest

from pinser.runtime.tools import ReadTool, ToolArgumentError
from pinser.runtime.tools.protocol import ToolInvocation


@pytest.mark.asyncio
async def test_read_tool_returns_file_contents(tmp_path: Path) -> None:
    (tmp_path / "note.txt").write_text("hello from file")
    tool = ReadTool(workspace_root=tmp_path)

    result = await tool.execute(ToolInvocation(tool_name="Read", arguments={"path": "note.txt"}))

    assert result.summary == "read note.txt"
    assert result.output == {
        "path": "note.txt",
        "content": "hello from file",
    }


def test_read_tool_requires_non_empty_path(tmp_path: Path) -> None:
    tool = ReadTool(workspace_root=tmp_path)

    with pytest.raises(ToolArgumentError, match="non-empty string path"):
        tool.build_permission_request(ToolInvocation(tool_name="Read", arguments={}))
