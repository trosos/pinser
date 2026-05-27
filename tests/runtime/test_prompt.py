from pinser.runtime.context.prompt import PromptRole, build_prompt_context
from pinser.runtime.engine.session import SessionState


def test_build_prompt_context_includes_system_history_and_new_user_message() -> None:
    session_state = SessionState(
        session_id="session-1",
        turn_count=1,
        transcript=["user: hello", "assistant: Echo: hello"],
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
