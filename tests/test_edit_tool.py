from pathlib import Path

import pytest

from pinser.runtime.engine.file_state import FileStateTracker
from pinser.runtime.tools import EditTool
from pinser.runtime.tools.protocol import ToolInvocation
from pinser.runtime.tools_errors import ToolArgumentError, ToolSafetyBlockedError


@pytest.mark.asyncio
async def test_edit_tool_replaces_exact_match_and_returns_diff(tmp_path: Path) -> None:
    file_path = tmp_path / "notes.txt"
    file_path.write_text("alpha\nbeta\n")
    tracker = FileStateTracker(workspace_root=tmp_path)
    tracker.record_read("notes.txt", "alpha\nbeta\n")
    tool = EditTool(workspace_root=tmp_path, file_state=tracker)

    result = await tool.execute(
        ToolInvocation(
            tool_name="Edit",
            arguments={
                "path": "notes.txt",
                "old_string": "beta",
                "new_string": "gamma",
            },
        )
    )

    assert file_path.read_text() == "alpha\ngamma\n"
    assert result.summary == "edited notes.txt"
    assert result.output["type"] == "update"
    assert result.output["replacements"] == 1
    assert result.output["diff"] == [
        "--- a/notes.txt",
        "+++ b/notes.txt",
        "@@ -1,2 +1,2 @@",
        " alpha",
        "-beta",
        "+gamma",
    ]
    tracker.require_safe_overwrite("notes.txt", "alpha\ngamma\n")


@pytest.mark.asyncio
async def test_edit_tool_requires_prior_read(tmp_path: Path) -> None:
    file_path = tmp_path / "notes.txt"
    file_path.write_text("alpha\nbeta\n")
    tool = EditTool(
        workspace_root=tmp_path,
        file_state=FileStateTracker(workspace_root=tmp_path),
    )

    with pytest.raises(ToolSafetyBlockedError, match="requires prior read"):
        await tool.execute(
            ToolInvocation(
                tool_name="Edit",
                arguments={
                    "path": "notes.txt",
                    "old_string": "beta",
                    "new_string": "gamma",
                },
            )
        )


@pytest.mark.asyncio
async def test_edit_tool_rejects_multiple_matches_without_replace_all(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "notes.txt"
    file_path.write_text("beta\nbeta\n")
    tracker = FileStateTracker(workspace_root=tmp_path)
    tracker.record_read("notes.txt", "beta\nbeta\n")
    tool = EditTool(workspace_root=tmp_path, file_state=tracker)

    with pytest.raises(ToolArgumentError, match="must match exactly once"):
        await tool.execute(
            ToolInvocation(
                tool_name="Edit",
                arguments={
                    "path": "notes.txt",
                    "old_string": "beta",
                    "new_string": "gamma",
                },
            )
        )


@pytest.mark.asyncio
async def test_edit_tool_can_replace_all_matches(tmp_path: Path) -> None:
    file_path = tmp_path / "notes.txt"
    file_path.write_text("beta\nbeta\n")
    tracker = FileStateTracker(workspace_root=tmp_path)
    tracker.record_read("notes.txt", "beta\nbeta\n")
    tool = EditTool(workspace_root=tmp_path, file_state=tracker)

    result = await tool.execute(
        ToolInvocation(
            tool_name="Edit",
            arguments={
                "path": "notes.txt",
                "old_string": "beta",
                "new_string": "gamma",
                "replace_all": True,
            },
        )
    )

    assert file_path.read_text() == "gamma\ngamma\n"
    assert result.output["replacements"] == 2


@pytest.mark.asyncio
async def test_edit_tool_rejects_notebook_paths(tmp_path: Path) -> None:
    file_path = tmp_path / "notebook.ipynb"
    file_path.write_text('{"cells": []}\n')
    tracker = FileStateTracker(workspace_root=tmp_path)
    tracker.record_read("notebook.ipynb", '{"cells": []}\n')
    tool = EditTool(workspace_root=tmp_path, file_state=tracker)

    with pytest.raises(ToolArgumentError, match="notebook-specific tool"):
        await tool.execute(
            ToolInvocation(
                tool_name="Edit",
                arguments={
                    "path": "notebook.ipynb",
                    "old_string": "[]",
                    "new_string": "[1]",
                },
            )
        )


def test_edit_tool_requires_non_empty_path(tmp_path: Path) -> None:
    tool = EditTool(workspace_root=tmp_path)

    with pytest.raises(ToolArgumentError, match="non-empty string path"):
        tool.build_permission_request(ToolInvocation(tool_name="Edit", arguments={}))


def test_edit_tool_denies_protected_workspace_path(tmp_path: Path) -> None:
    tool = EditTool(workspace_root=tmp_path)

    decision = tool.decide_permission(
        ToolInvocation(
            tool_name="Edit",
            arguments={
                "path": ".git/config",
                "old_string": "a",
                "new_string": "b",
            },
        )
    )

    assert decision.is_deny
    assert decision.reason == "protected-path"
