from pathlib import Path

from pinser.app.config.settings import load_settings


def test_load_settings_uses_workspace_root(tmp_path: Path) -> None:
    settings = load_settings(tmp_path)

    assert settings.app_name == "pinser"
    assert settings.paths.workspace_root == tmp_path.resolve()
    assert settings.paths.state_dir == tmp_path.resolve() / ".pinser"
