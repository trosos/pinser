from pathlib import Path

from typer.testing import CliRunner

from pinser.app.cli.main import app


def test_cli_runs_successfully(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["main", "--workspace", str(tmp_path)])

    assert result.exit_code == 0
    assert "Pinser is initialized and ready to grow." in result.stdout
    assert str(tmp_path.resolve()) in result.stdout


def test_run_turn_command_streams_runtime_events(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["run-turn", "hello", "--workspace", str(tmp_path)])

    assert result.exit_code == 0
    assert "turn-started turn_id=1 user=hello" in result.stdout
    assert "user: hello" in result.stdout
    assert "assistant: Echo: hello" in result.stdout
    assert "turn-completed turn_id=1" in result.stdout
