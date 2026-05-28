from pathlib import Path

from pinser.runtime import PathSafety


def test_path_safety_resolves_relative_paths_inside_workspace(tmp_path: Path) -> None:
    safety = PathSafety(tmp_path)

    resolved = safety.resolve("src/main.py")

    assert resolved.expanded == tmp_path / "src/main.py"
    assert resolved.workspace_relative == "src/main.py"
    assert resolved.comparison_path.endswith("/src/main.py")


def test_path_safety_blocks_paths_outside_workspace(tmp_path: Path) -> None:
    safety = PathSafety(tmp_path)

    decision = safety.check_read_path("../secret.txt")

    assert not decision.allowed
    assert decision.reason == "path-outside-workspace"
    assert not decision.requires_approval


def test_path_safety_marks_network_like_paths_as_manual_approval(tmp_path: Path) -> None:
    safety = PathSafety(tmp_path)

    decision = safety.check_read_path("//server/share/file.txt")

    assert not decision.allowed
    assert decision.reason == "network-path-requires-approval"
    assert decision.requires_approval


def test_path_safety_blocks_known_special_read_paths(tmp_path: Path) -> None:
    safety = PathSafety(tmp_path)

    decision = safety.check_read_path("/dev/zero")

    assert not decision.allowed
    assert decision.reason == "blocked-special-file"
