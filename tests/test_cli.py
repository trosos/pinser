from pathlib import Path

from typer.testing import CliRunner

from pinser.app.cli.main import app


def test_cli_runs_successfully(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["--workspace", str(tmp_path)])

    assert result.exit_code == 0
    assert "Pinser is initialized and ready to grow." in result.stdout
    assert str(tmp_path.resolve()) in result.stdout
