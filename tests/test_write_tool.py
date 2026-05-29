from pathlib import Path

import pytest

from pinser.runtime.engine.file_state import FileStateTracker
from pinser.runtime.tools import WriteTool
from pinser.runtime.tools.protocol import ToolInvocation
from pinser.runtime.tools_errors import ToolArgumentError, ToolSafetyBlockedError


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


@pytest.mark.asyncio
async def test_write_tool_requires_prior_read_for_existing_file(tmp_path: Path) -> None:
    file_path = tmp_path / "notes.txt"
    file_path.write_text("old\nvalue\n")
    tracker = FileStateTracker(workspace_root=tmp_path)
    tool = WriteTool(workspace_root=tmp_path, file_state=tracker)

    with pytest.raises(ToolSafetyBlockedError, match="requires prior read"):
        await tool.execute(
            ToolInvocation(
                tool_name="Write",
                arguments={"path": "notes.txt", "content": "new\nvalue\n"},
            )
        )


@pytest.mark.asyncio
async def test_write_tool_allows_overwrite_after_matching_prior_read(tmp_path: Path) -> None:
    file_path = tmp_path / "notes.txt"
    file_path.write_text("old\nvalue\n")
    tracker = FileStateTracker(workspace_root=tmp_path)
    tracker.record_read("notes.txt", "old\nvalue\n")
    tool = WriteTool(workspace_root=tmp_path, file_state=tracker)

    result = await tool.execute(
        ToolInvocation(
            tool_name="Write",
            arguments={"path": "notes.txt", "content": "new\nvalue\n"},
        )
    )

    assert file_path.read_text() == "new\nvalue\n"
    assert result.summary == "updated notes.txt"
    tracker.require_safe_overwrite("notes.txt", "new\nvalue\n")


@pytest.mark.asyncio
async def test_write_tool_rejects_file_changed_after_prior_read(tmp_path: Path) -> None:
    file_path = tmp_path / "notes.txt"
    file_path.write_text("old\nvalue\n")
    tracker = FileStateTracker(workspace_root=tmp_path)
    tracker.record_read("notes.txt", "old\nvalue\n")
    file_path.write_text("external change\n")
    tool = WriteTool(workspace_root=tmp_path, file_state=tracker)

    with pytest.raises(ToolSafetyBlockedError, match="file changed since last read"):
        await tool.execute(
            ToolInvocation(
                tool_name="Write",
                arguments={"path": "notes.txt", "content": "new\nvalue\n"},
            )
        )


def test_write_tool_requires_non_empty_path(tmp_path: Path) -> None:
    tool = WriteTool(workspace_root=tmp_path)

    with pytest.raises(ToolArgumentError, match="non-empty string path"):
        tool.build_permission_request(ToolInvocation(tool_name="Write", arguments={}))


def test_write_tool_requires_string_content(tmp_path: Path) -> None:
    tool = WriteTool(workspace_root=tmp_path)

    with pytest.raises(ToolArgumentError, match="string content argument"):
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
