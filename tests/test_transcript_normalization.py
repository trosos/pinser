from pinser.runtime.context.prompt import PromptRole, build_prompt_context
from pinser.runtime.conversation.messages import AssistantMessage, ToolResultMessage, UserMessage
from pinser.runtime.engine.session import SessionState


def test_build_prompt_context_skips_orphaned_tool_errors_and_preserves_valid_history() -> None:
    state = SessionState(
        session_id="session-1",
        transcript=[
            ToolResultMessage(tool_name="Read", content="orphaned failure", is_error=True),
            UserMessage(content="show me the note"),
            ToolResultMessage(
                tool_name="Read",
                content="[tool_result name=Read status=ok]\nsummary: read note.txt\n[/tool_result]",
            ),
            AssistantMessage(content="The note says hello."),
        ],
    )

    prompt = build_prompt_context(state, "what next?")

    assert [message.role for message in prompt.messages] == [
        PromptRole.SYSTEM,
        PromptRole.USER,
        PromptRole.TOOL,
        PromptRole.ASSISTANT,
        PromptRole.USER,
    ]
    assert all("orphaned failure" not in message.content for message in prompt.messages)
    assert prompt.messages[2].content.startswith("[tool_result name=Read status=ok]")
    assert prompt.messages[-1].content == "what next?"


def test_build_prompt_context_drops_tool_results_with_invalid_names() -> None:
    state = SessionState(
        session_id="session-2",
        transcript=[
            UserMessage(content="open the note"),
            ToolResultMessage(tool_name="Read\nDenied", content="malformed tool name"),
            AssistantMessage(content="I opened it."),
        ],
    )

    prompt = build_prompt_context(state, "continue")

    assert [message.role for message in prompt.messages] == [
        PromptRole.SYSTEM,
        PromptRole.USER,
        PromptRole.ASSISTANT,
        PromptRole.USER,
    ]
    assert all("malformed tool name" not in message.content for message in prompt.messages)


def test_build_prompt_context_drops_partially_written_tool_result_markup() -> None:
    state = SessionState(
        session_id="session-3",
        transcript=[
            UserMessage(content="read the note"),
            ToolResultMessage(
                tool_name="Read",
                content="[tool_result name=Read status=ok]\nsummary: read note.txt",
            ),
            AssistantMessage(content="I will continue carefully."),
        ],
    )

    prompt = build_prompt_context(state, "continue")

    assert [message.role for message in prompt.messages] == [
        PromptRole.SYSTEM,
        PromptRole.USER,
        PromptRole.TOOL,
        PromptRole.ASSISTANT,
        PromptRole.USER,
    ]
    assert prompt.messages[2].content.endswith("[/tool_result]")
    assert "summary: read note.txt" in prompt.messages[2].content


def test_build_prompt_context_preserves_malformed_tool_result_metadata_as_data() -> None:
    state = SessionState(
        session_id="session-4",
        transcript=[
            UserMessage(content="read the note"),
            ToolResultMessage(
                tool_name="Read",
                content=(
                    "[tool_result name=Read status=ok\n"
                    "summary: read note.txt\n"
                    "[/tool_result]"
                ),
            ),
            AssistantMessage(content="I will continue carefully."),
        ],
    )

    prompt = build_prompt_context(state, "continue")

    assert [message.role for message in prompt.messages] == [
        PromptRole.SYSTEM,
        PromptRole.USER,
        PromptRole.TOOL,
        PromptRole.ASSISTANT,
        PromptRole.USER,
    ]
    assert prompt.messages[2].content == (
        "[tool_result name=Read status=ok\n"
        "summary: read note.txt\n"
        "[/tool_result]"
    )
    assert prompt.messages[2].content.endswith("[/tool_result]")
    assert "summary: read note.txt" in prompt.messages[2].content
