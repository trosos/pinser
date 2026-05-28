from pathlib import Path

import pytest
from support_models import SequenceModel

from pinser.runtime.engine.session import Session, SessionState
from pinser.runtime.events.models import (
    AssistantMessageEvent,
    PermissionRequiredEvent,
    ToolCompletedEvent,
    ToolDeniedEvent,
    ToolStartedEvent,
)
from pinser.runtime.model.messages import AssistantStep, ToolCall
from pinser.runtime.tools import ReadTool, ToolRegistry


@pytest.mark.asyncio
async def test_session_runs_read_tool_and_emits_tool_events(tmp_path: Path) -> None:
    file_path = tmp_path / "note.txt"
    file_path.write_text("hello from file")

    registry = ToolRegistry()
    registry.register(ReadTool(workspace_root=tmp_path))
    model = SequenceModel(
        responses=[
            AssistantStep(tool_call=ToolCall(tool_name="Read", arguments={"path": "note.txt"}))
        ]
    )
    session = Session(
        SessionState(session_id="session-1"),
        model,
        workspace_root=tmp_path,
        tools=registry,
    )

    events = [event async for event in session.run_turn("read the note")]

    assert isinstance(events[3], ToolStartedEvent)
    assert events[3].summary == "read note.txt"
    assert isinstance(events[4], ToolCompletedEvent)
    assert events[4].summary == "read note.txt"
    assert isinstance(events[5], AssistantMessageEvent)
    assert events[5].message == "hello from file"


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

    assert isinstance(events[3], ToolStartedEvent)
    assert isinstance(events[4], PermissionRequiredEvent)
    assert isinstance(events[5], ToolDeniedEvent)
    assert isinstance(events[6], AssistantMessageEvent)
    assert events[6].message == "Denied: approval-required action blocked by dontAsk mode."
