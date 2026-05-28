from pathlib import Path

import pytest

from pinser.runtime.tools import WriteTool
from pinser.runtime.tools.protocol import ToolInvocation


@pytest.mark.asyncio
async def test_write_tool_creates_workspace_file_with_diff(tmp_path: Path) -> None:
    tool = WriteTool(workspace_root=tmp_path)

    result = await tool.execute(
        ToolInvocation(
            tool_name="Write",
            arguments={"path": "notes/todo.txt", "content": "hello\nworld\n"},
        )
    )

    assert (tmp_path / "notes" / "todo.txt").read_text() == "hello\nworld\n"
    assert result.summary == "created notes/todo.txt"
    assert result.output["type"] == "create"
    assert result.output["path"] == "notes/todo.txt"
    assert result.output["original_content"] is None
    assert result.output["content"] == "hello\nworld\n"
    assert result.output["diff"] == [
        "--- a/notes/todo.txt",
        "+++ b/notes/todo.txt",
        "@@ -0,0 +1,2 @@",
        "+hello",
        "+world",
    ]


@pytest.mark.asyncio
async def test_write_tool_updates_existing_workspace_file(tmp_path: Path) -> None:
    file_path = tmp_path / "notes.txt"
    file_path.write_text("old\nvalue\n")
    tool = WriteTool(workspace_root=tmp_path)

    result = await tool.execute(
        ToolInvocation(
            tool_name="Write",
            arguments={"path": "notes.txt", "content": "new\nvalue\n"},
        )
    )

    assert file_path.read_text() == "new\nvalue\n"
    assert result.summary == "updated notes.txt"
    assert result.output["type"] == "update"
    assert result.output["original_content"] == "old\nvalue\n"


def test_write_tool_requires_non_empty_path(tmp_path: Path) -> None:
    tool = WriteTool(workspace_root=tmp_path)

    with pytest.raises(ValueError, match="non-empty string path"):
        tool.build_permission_request(ToolInvocation(tool_name="Write", arguments={}))


def test_write_tool_requires_string_content(tmp_path: Path) -> None:
    tool = WriteTool(workspace_root=tmp_path)

    with pytest.raises(ValueError, match="string content argument"):
        tool._require_content(ToolInvocation(tool_name="Write", arguments={"path": "a.txt"}))


def test_write_tool_denies_protected_workspace_path(tmp_path: Path) -> None:
    tool = WriteTool(workspace_root=tmp_path)

    decision = tool.decide_permission(
        ToolInvocation(
            tool_name="Write",
            arguments={"path": ".git/config", "content": "x"},
        )
    )

    assert decision.is_deny
    assert decision.reason == "protected-path"
