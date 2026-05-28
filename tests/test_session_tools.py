from pathlib import Path

import pytest
from support_models import SequenceModel

from pinser.runtime.context.prompt import PromptRole
from pinser.runtime.engine.session import Session, SessionState
from pinser.runtime.events.models import (
    AssistantMessageEvent,
    PermissionRequiredEvent,
    ProgressEvent,
    ToolBlockedEvent,
    ToolCompletedEvent,
    ToolDeniedEvent,
    ToolStartedEvent,
)
from pinser.runtime.model.messages import AssistantStep, ToolCall
from pinser.runtime.tools import EditTool, GrepTool, ReadTool, ToolRegistry, WriteTool


@pytest.mark.asyncio
async def test_session_runs_read_tool_then_generates_assistant_reply(tmp_path: Path) -> None:
    file_path = tmp_path / "note.txt"
    file_path.write_text("hello from file")

    registry = ToolRegistry()
    registry.register(ReadTool(workspace_root=tmp_path))
    model = SequenceModel(
        responses=[
            AssistantStep(tool_call=ToolCall(tool_name="Read", arguments={"path": "note.txt"})),
            AssistantStep(message="I read the note: hello from file"),
        ]
    )
    session = Session(
        SessionState(session_id="session-1", workspace_root=tmp_path),
        model,
        workspace_root=tmp_path,
        tools=registry,
    )

    events = [event async for event in session.run_turn("read the note")]

    assert isinstance(events[2], ProgressEvent)
    assert events[2].stage == "generating"
    assert isinstance(events[3], ToolStartedEvent)
    assert events[3].summary == "read note.txt"
    assert isinstance(events[4], ToolCompletedEvent)
    assert events[4].summary == "read note.txt"
    assert isinstance(events[5], AssistantMessageEvent)
    assert events[5].message == "I read the note: hello from file"
    assert len(model.prompts) == 2
    assert [message.role for message in model.prompts[1].messages] == [
        PromptRole.SYSTEM,
        PromptRole.USER,
        PromptRole.TOOL,
        PromptRole.USER,
    ]
    assert model.prompts[1].messages[1].content == "read the note"
    assert model.prompts[1].messages[2].content == "hello from file"
    assert model.prompts[1].messages[3].content == "read the note"


@pytest.mark.asyncio
async def test_session_denies_read_tool_when_path_needs_approval(tmp_path: Path) -> None:
    registry = ToolRegistry()
    registry.register(ReadTool(workspace_root=tmp_path))
    model = SequenceModel(
        responses=[
            AssistantStep(
                tool_call=ToolCall(
                    tool_name="Read",
                    arguments={"path": "//server/share/note.txt"},
                )
            )
        ]
    )
    session = Session(
        SessionState(session_id="session-1", workspace_root=tmp_path),
        model,
        workspace_root=tmp_path,
        tools=registry,
    )

    events = [event async for event in session.run_turn("read the network note")]

    assert isinstance(events[2], ProgressEvent)
    assert events[2].stage == "generating"
    assert isinstance(events[3], ToolStartedEvent)
    assert isinstance(events[4], PermissionRequiredEvent)
    assert isinstance(events[5], ToolDeniedEvent)
    assert isinstance(events[6], AssistantMessageEvent)
    assert events[6].message == "Denied: approval-required action blocked by dontAsk mode."


@pytest.mark.asyncio
async def test_session_stops_after_maximum_assistant_tool_steps(tmp_path: Path) -> None:
    file_path = tmp_path / "note.txt"
    file_path.write_text("hello from file")

    registry = ToolRegistry()
    registry.register(ReadTool(workspace_root=tmp_path))
    model = SequenceModel(
        responses=[
            AssistantStep(tool_call=ToolCall(tool_name="Read", arguments={"path": "note.txt"}))
            for _ in range(8)
        ]
    )
    session = Session(
        SessionState(session_id="session-1", workspace_root=tmp_path),
        model,
        workspace_root=tmp_path,
        tools=registry,
    )

    events = [event async for event in session.run_turn("keep reading the note")]

    assert isinstance(events[-2], AssistantMessageEvent)
    assert (
        events[-2].message
        == "Stopped: exceeded maximum assistant/tool steps for a single turn."
    )


@pytest.mark.asyncio
async def test_session_runs_grep_tool_then_generates_assistant_reply(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("alpha\nTODO one\n")
    (tmp_path / "b.txt").write_text("TODO two\n")

    registry = ToolRegistry()
    registry.register(GrepTool(workspace_root=tmp_path))
    model = SequenceModel(
        responses=[
            AssistantStep(
                tool_call=ToolCall(
                    tool_name="Grep",
                    arguments={"pattern": "TODO", "glob": "**/*.txt"},
                )
            ),
            AssistantStep(message="I found TODO in two lines."),
        ]
    )
    session = Session(
        SessionState(session_id="session-1", workspace_root=tmp_path),
        model,
        workspace_root=tmp_path,
        tools=registry,
    )

    events = [event async for event in session.run_turn("search for TODO")]

    assert isinstance(events[2], ProgressEvent)
    assert events[2].stage == "generating"
    assert isinstance(events[3], ToolStartedEvent)
    assert events[3].summary == "grep TODO"
    assert isinstance(events[4], ToolCompletedEvent)
    assert events[4].summary == "matched 2 line(s)"
    assert isinstance(events[5], AssistantMessageEvent)
    assert events[5].message == "I found TODO in two lines."
    assert len(model.prompts) == 2
    assert [message.role for message in model.prompts[1].messages] == [
        PromptRole.SYSTEM,
        PromptRole.USER,
        PromptRole.TOOL,
        PromptRole.USER,
    ]
    assert model.prompts[1].messages[2].content == "matched 2 line(s)"


@pytest.mark.asyncio
async def test_session_allows_write_after_runtime_read(tmp_path: Path) -> None:
    file_path = tmp_path / "note.txt"
    file_path.write_text("old\nvalue\n")

    state = SessionState(session_id="session-1", workspace_root=tmp_path)
    registry = ToolRegistry()
    registry.register(ReadTool(workspace_root=tmp_path, file_state=state.file_state))
    registry.register(WriteTool(workspace_root=tmp_path, file_state=state.file_state))
    model = SequenceModel(
        responses=[
            AssistantStep(tool_call=ToolCall(tool_name="Read", arguments={"path": "note.txt"})),
            AssistantStep(
                tool_call=ToolCall(
                    tool_name="Write",
                    arguments={"path": "note.txt", "content": "new\nvalue\n"},
                )
            ),
            AssistantStep(message="Updated the note."),
        ]
    )
    session = Session(state, model, workspace_root=tmp_path, tools=registry)

    events = [event async for event in session.run_turn("read and update the note")]

    assert file_path.read_text() == "new\nvalue\n"
    assert isinstance(events[3], ToolStartedEvent)
    assert events[3].summary == "read note.txt"
    assert isinstance(events[4], ToolCompletedEvent)
    assert events[4].summary == "read note.txt"
    assert isinstance(events[5], ToolStartedEvent)
    assert events[5].summary == "write note.txt"
    assert isinstance(events[6], ToolCompletedEvent)
    assert events[6].summary == "updated note.txt"
    assert isinstance(events[7], AssistantMessageEvent)
    assert events[7].message == "Updated the note."


@pytest.mark.asyncio
async def test_session_rejects_write_without_runtime_read(tmp_path: Path) -> None:
    file_path = tmp_path / "note.txt"
    file_path.write_text("old\nvalue\n")

    state = SessionState(session_id="session-2", workspace_root=tmp_path)
    registry = ToolRegistry()
    registry.register(WriteTool(workspace_root=tmp_path, file_state=state.file_state))
    model = SequenceModel(
        responses=[
            AssistantStep(
                tool_call=ToolCall(
                    tool_name="Write",
                    arguments={"path": "note.txt", "content": "new\nvalue\n"},
                )
            )
        ]
    )
    session = Session(state, model, workspace_root=tmp_path, tools=registry)

    events = [event async for event in session.run_turn("update the note")]

    assert file_path.read_text() == "old\nvalue\n"
    assert isinstance(events[3], ToolStartedEvent)
    assert events[3].summary == "write note.txt"
    assert isinstance(events[4], ToolBlockedEvent)
    assert events[4].reason == "write requires prior read for existing file"
    assert isinstance(events[5], AssistantMessageEvent)
    assert events[5].message == "Blocked: write requires prior read for existing file"


@pytest.mark.asyncio
async def test_session_runs_edit_tool_then_generates_assistant_reply(tmp_path: Path) -> None:
    file_path = tmp_path / "note.txt"
    file_path.write_text("alpha\nbeta\n")

    state = SessionState(session_id="session-3", workspace_root=tmp_path)
    registry = ToolRegistry()
    registry.register(ReadTool(workspace_root=tmp_path, file_state=state.file_state))
    registry.register(EditTool(workspace_root=tmp_path, file_state=state.file_state))
    model = SequenceModel(
        responses=[
            AssistantStep(tool_call=ToolCall(tool_name="Read", arguments={"path": "note.txt"})),
            AssistantStep(
                tool_call=ToolCall(
                    tool_name="Edit",
                    arguments={
                        "path": "note.txt",
                        "old_string": "beta",
                        "new_string": "gamma",
                    },
                )
            ),
            AssistantStep(message="Updated the matching line."),
        ]
    )
    session = Session(state, model, workspace_root=tmp_path, tools=registry)

    events = [event async for event in session.run_turn("replace beta with gamma")]

    assert file_path.read_text() == "alpha\ngamma\n"
    assert isinstance(events[3], ToolStartedEvent)
    assert events[3].summary == "read note.txt"
    assert isinstance(events[4], ToolCompletedEvent)
    assert events[4].summary == "read note.txt"
    assert isinstance(events[5], ToolStartedEvent)
    assert events[5].summary == "edit note.txt"
    assert isinstance(events[6], ToolCompletedEvent)
    assert events[6].summary == "edited note.txt"
    assert isinstance(events[7], AssistantMessageEvent)
    assert events[7].message == "Updated the matching line."
    assert len(model.prompts) == 3
    assert [message.role for message in model.prompts[2].messages] == [
        PromptRole.SYSTEM,
        PromptRole.USER,
        PromptRole.TOOL,
        PromptRole.TOOL,
        PromptRole.USER,
    ]
    assert model.prompts[2].messages[2].content == "alpha\nbeta\n"
    assert model.prompts[2].messages[3].content == "alpha\ngamma\n"
    assert model.prompts[2].messages[4].content == "replace beta with gamma"


@pytest.mark.asyncio
async def test_session_rejects_edit_without_runtime_read(tmp_path: Path) -> None:
    file_path = tmp_path / "note.txt"
    file_path.write_text("alpha\nbeta\n")

    state = SessionState(session_id="session-4", workspace_root=tmp_path)
    registry = ToolRegistry()
    registry.register(EditTool(workspace_root=tmp_path, file_state=state.file_state))
    model = SequenceModel(
        responses=[
            AssistantStep(
                tool_call=ToolCall(
                    tool_name="Edit",
                    arguments={
                        "path": "note.txt",
                        "old_string": "beta",
                        "new_string": "gamma",
                    },
                )
            )
        ]
    )
    session = Session(state, model, workspace_root=tmp_path, tools=registry)

    events = [event async for event in session.run_turn("replace beta with gamma")]

    assert file_path.read_text() == "alpha\nbeta\n"
    assert isinstance(events[3], ToolStartedEvent)
    assert events[3].summary == "edit note.txt"
    assert isinstance(events[4], ToolBlockedEvent)
    assert events[4].reason == "edit requires prior read for existing file"
    assert isinstance(events[5], AssistantMessageEvent)
    assert events[5].message == "Blocked: edit requires prior read for existing file"
