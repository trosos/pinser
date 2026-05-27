from pathlib import Path

from typer.testing import CliRunner

from pinser.app.cli.main import app


def test_cli_runs_successfully(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["main", "--workspace", str(tmp_path)])

    assert result.exit_code == 0
    assert "Pinser initialized." in result.stdout
    assert f"workspace={tmp_path.resolve()}" in result.stdout
    assert "state_dir=" in result.stdout


def test_run_turn_command_streams_runtime_events(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["run-turn", "hello", "--workspace", str(tmp_path)])

    assert result.exit_code == 0
    assert "turn-started turn_id=1 user_message='hello'" in result.stdout
    assert "user-message turn_id=1 content='hello'" in result.stdout
    assert "Progress: turn_id=1 stage=generating" in result.stdout
    assert "assistant-message turn_id=1 content='Echo: hello'" in result.stdout
    assert "turn-completed turn_id=1" in result.stdout

