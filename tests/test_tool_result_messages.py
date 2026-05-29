from pathlib import Path

from support_models import SequenceModel

from pinser.runtime.context.tool_result_rendering import (
    format_tool_message_for_prompt,
    render_tool_result_for_prompt,
)
from pinser.runtime.conversation.messages import ToolResultMessage
from pinser.runtime.engine.session import Session, SessionState
from pinser.runtime.model.messages import AssistantStep, ToolCall
from pinser.runtime.tools import ReadTool, ToolRegistry
from pinser.runtime.tools.protocol import ToolExecutionResult


def test_render_tool_result_for_prompt_includes_summary_and_structured_output() -> None:
    result = ToolExecutionResult(
        summary="matched 2 line(s)",
        output={
            "pattern": "TODO",
            "matches": [
                {"path": "a.txt", "line_number": 2, "line": "TODO one"},
                {"path": "b.txt", "line_number": 1, "line": "TODO two"},
            ],
        },
    )

    rendered = render_tool_result_for_prompt("Grep", result)

    assert rendered.startswith("[tool_result name=Grep status=ok]\nsummary: matched 2 line(s)")
    assert "pattern:" in rendered
    assert "matches:" in rendered
    assert "TODO one" in rendered
    assert rendered.endswith("[/tool_result]")


def test_render_tool_result_for_prompt_truncates_large_output() -> None:
    result = ToolExecutionResult(
        summary="read note.txt",
        output={"content": "x" * 5000},
    )

    rendered = render_tool_result_for_prompt("Read", result)

    assert "truncated" in rendered
    assert rendered.startswith("[tool_result name=Read status=ok]")


async def test_session_stores_rendered_tool_result_in_transcript(tmp_path: Path) -> None:
    file_path = tmp_path / "note.txt"
    file_path.write_text("hello from file")

    registry = ToolRegistry()
    registry.register(ReadTool(workspace_root=tmp_path))
    model = SequenceModel(
        responses=[
            AssistantStep(tool_call=ToolCall(tool_name="Read", arguments={"path": "note.txt"})),
            AssistantStep(message="done"),
        ]
    )
    session = Session(
        SessionState(session_id="session-1"),
        model,
        workspace_root=tmp_path,
        tools=registry,
    )

    _ = [event async for event in session.run_turn("read the note")]

    tool_result = session.state.transcript[1]
    assert isinstance(tool_result, ToolResultMessage)
    assert tool_result.content.startswith(
        "[tool_result name=Read status=ok]\nsummary: read note.txt"
    )
    assert "hello from file" in tool_result.content


def test_format_tool_message_for_prompt_is_idempotent_for_rendered_content() -> None:
    rendered = (
        "[tool_result name=Read status=ok]\n"
        "summary: read note.txt\n"
        "[/tool_result]"
    )

    assert format_tool_message_for_prompt("Read", rendered, False) == rendered
