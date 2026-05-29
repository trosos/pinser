from pinser.runtime.context.tool_result_rendering import render_tool_result_for_prompt
from pinser.runtime.tools.protocol import ToolExecutionResult


def test_render_tool_result_for_prompt_redacts_api_key_like_values() -> None:
    result = ToolExecutionResult(
        summary="read config.env",
        output={"content": "API_KEY=sk-super-secret-token"},
    )

    rendered = render_tool_result_for_prompt("Read", result)

    assert "sk-super-secret-token" not in rendered
    assert "API_KEY=[REDACTED]" in rendered


def test_render_tool_result_for_prompt_redacts_bearer_tokens_in_nested_output() -> None:
    result = ToolExecutionResult(
        summary="fetched headers",
        output={"headers": {"Authorization": "Bearer top-secret-token"}},
    )

    rendered = render_tool_result_for_prompt("WebFetch", result)

    assert "top-secret-token" not in rendered
    assert "Bearer [REDACTED]" in rendered
