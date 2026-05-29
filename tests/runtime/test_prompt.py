from pinser.runtime.context.prompt import PromptRole, build_prompt_context
from pinser.runtime.conversation.messages import AssistantMessage, ToolResultMessage, UserMessage
from pinser.runtime.engine.session import SessionState


def test_build_prompt_context_includes_system_history_and_new_user_message() -> None:
    session_state = SessionState(
        session_id="session-1",
        turn_count=1,
        transcript=[UserMessage(content="hello"), AssistantMessage(content="Echo: hello")],
    )

    prompt_context = build_prompt_context(session_state, "what next?")

    assert prompt_context.session_id == "session-1"
    assert prompt_context.turn_id == 2
    assert [message.role for message in prompt_context.messages] == [
        PromptRole.SYSTEM,
        PromptRole.USER,
        PromptRole.ASSISTANT,
        PromptRole.USER,
    ]
    assert prompt_context.messages[-1].content == "what next?"


def test_build_prompt_context_wraps_tool_messages_with_explicit_untrusted_framing() -> None:
    session_state = SessionState(
        session_id="session-1",
        turn_count=1,
        transcript=[
            UserMessage(content="hello"),
            ToolResultMessage(tool_name="Read", content="file content"),
        ],
    )

    prompt_context = build_prompt_context(session_state, "what next?")

    assert prompt_context.messages[2].role is PromptRole.TOOL
    assert prompt_context.messages[2].content == (
        "[tool_result name=Read status=ok]\n"
        "file content\n"
        "[/tool_result]"
    )


def test_build_prompt_context_marks_error_tool_messages() -> None:
    session_state = SessionState(
        session_id="session-1",
        turn_count=1,
        transcript=[
            UserMessage(content="hello"),
            ToolResultMessage(
                tool_name="Write",
                content="permission denied",
                is_error=True,
            ),
        ],
    )

    prompt_context = build_prompt_context(session_state, "what next?")

    assert prompt_context.messages[2].content == (
        "[tool_result name=Write status=error]\n"
        "permission denied\n"
        "[/tool_result]"
    )
