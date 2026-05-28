from pathlib import Path

import pytest
from support_models import SequenceModel

from pinser.runtime.context.prompt import PromptRole
from pinser.runtime.engine.session import Session, SessionState
from pinser.runtime.events.models import (
    AssistantMessageEvent,
    PermissionRequiredEvent,
    ProgressEvent,
    ToolCompletedEvent,
    ToolDeniedEvent,
    ToolStartedEvent,
)
from pinser.runtime.model.messages import AssistantStep, ToolCall
from pinser.runtime.tools import ReadTool, ToolRegistry


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
        SessionState(session_id="session-1"),
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
        SessionState(session_id="session-1"),
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
        SessionState(session_id="session-1"),
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
    assert len(model.prompts) == 8

