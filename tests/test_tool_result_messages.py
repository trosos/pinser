from pathlib import Path

import pytest
from support_models import SequenceModel

from pinser.runtime.context.prompt import PromptRole, build_prompt_context
from pinser.runtime.conversation.messages import AssistantMessage, ToolResultMessage, UserMessage
from pinser.runtime.engine.session import Session, SessionState
from pinser.runtime.model.messages import AssistantStep, ToolCall
from pinser.runtime.tools import ReadTool, ToolRegistry


@pytest.mark.asyncio
async def test_tool_results_are_stored_explicitly_in_transcript(tmp_path: Path) -> None:
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

    _ = [event async for event in session.run_turn("read the note")]

    assert len(session.state.transcript) == 3
    assert isinstance(session.state.transcript[0], UserMessage)
    assert session.state.transcript[0].content == "read the note"
    assert isinstance(session.state.transcript[1], ToolResultMessage)
    assert session.state.transcript[1].tool_name == "Read"
    assert session.state.transcript[1].content == "hello from file"
    assert isinstance(session.state.transcript[2], AssistantMessage)
    assert session.state.transcript[2].content == "hello from file"


def test_prompt_context_includes_explicit_tool_role_messages() -> None:
    state = SessionState(
        session_id="session-1",
        turn_count=1,
        transcript=[],
    )
    state.transcript.extend(
        [
            UserMessage(content="user prompt"),
            ToolResultMessage(tool_name="Read", content="file content"),
            AssistantMessage(content="assistant reply"),
        ]
    )

    prompt = build_prompt_context(state, "next user prompt")

    assert [message.role for message in prompt.messages] == [
        PromptRole.SYSTEM,
        PromptRole.USER,
        PromptRole.TOOL,
        PromptRole.ASSISTANT,
        PromptRole.USER,
    ]
    assert prompt.messages[2].content == "file content"
