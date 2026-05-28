from pathlib import Path

from typer.testing import CliRunner

from pinser.app.cli.main import _render_event, app
from pinser.runtime.events.models import (
    PermissionRequiredEvent,
    ToolBlockedEvent,
    ToolCompletedEvent,
    ToolDeniedEvent,
    ToolFailedEvent,
    ToolStartedEvent,
)
from pinser.runtime.permissions import PermissionDecisionKind

runner = CliRunner()


def test_root_help_uses_plain_consistent_output() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Usage: " in result.stdout
    assert "Pinser command-line interface." in result.stdout
    assert "Options:" in result.stdout
    assert "Commands:" in result.stdout
    assert "╭" not in result.stdout
    assert "│" not in result.stdout


def test_root_command_missing_subcommand_uses_plain_error_output() -> None:
    result = runner.invoke(app, [])

    assert result.exit_code != 0
    combined_output = result.stdout + result.stderr
    assert "Usage: " in combined_output
    assert "Try 'pinser --help' for help." in combined_output
    assert "Error: Missing command." in combined_output
    assert "╭" not in combined_output
    assert "│" not in combined_output


def test_cli_runs_successfully(tmp_path: Path) -> None:
    result = runner.invoke(app, ["main", "--workspace", str(tmp_path)])

    assert result.exit_code == 0
    assert "Pinser initialized." in result.stdout
    assert f"workspace={tmp_path.resolve()}" in result.stdout
    assert "state_dir=" in result.stdout


def test_run_turn_command_streams_runtime_events(tmp_path: Path) -> None:
    result = runner.invoke(app, ["run-turn", "hello", "--workspace", str(tmp_path)])

    assert result.exit_code == 0
    assert "turn-started turn_id=1 user=hello" in result.stdout
    assert "user: hello" in result.stdout
    assert "Progress: generating" in result.stdout
    assert "assistant: Echo: hello" in result.stdout
    assert "turn-completed turn_id=1" in result.stdout


def test_render_event_formats_phase_2_tool_events() -> None:
    assert (
        _render_event(
            ToolStartedEvent(
                session_id="session-1",
                turn_id=1,
                tool_name="Read",
                summary="path=/workspace/file.txt",
            )
        )
        == "tool-started tool=Read summary=path=/workspace/file.txt"
    )
    assert (
        _render_event(
            ToolCompletedEvent(
                session_id="session-1",
                turn_id=1,
                tool_name="Read",
                summary="path=/workspace/file.txt",
            )
        )
        == "tool-completed tool=Read summary=path=/workspace/file.txt"
    )
    assert (
        _render_event(
            PermissionRequiredEvent(
                session_id="session-1",
                turn_id=1,
                tool_name="Bash",
                summary="run Bash command in workspace.",
            )
        )
        == "Permission required: run Bash command in workspace."
    )
    assert (
        _render_event(
            ToolDeniedEvent(
                session_id="session-1",
                turn_id=1,
                tool_name="Bash",
                decision=PermissionDecisionKind.DENY,
                reason="approval-required action blocked by dontAsk mode.",
            )
        )
        == "Denied: approval-required action blocked by dontAsk mode."
    )
    assert (
        _render_event(
            ToolBlockedEvent(
                session_id="session-1",
                turn_id=1,
                tool_name="Edit",
                reason="file changed since last read: /workspace/file.txt.",
            )
        )
        == "Blocked: file changed since last read: /workspace/file.txt."
    )
    assert (
        _render_event(
            ToolFailedEvent(
                session_id="session-1",
                turn_id=1,
                tool_name="Bash",
                reason="command exited with status 1.",
            )
        )
        == "Error: command exited with status 1."
    )

