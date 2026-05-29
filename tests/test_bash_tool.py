import sys
import time
from pathlib import Path

import pytest

from pinser.runtime.permissions import PermissionDecisionKind
from pinser.runtime.tools import BashPermissionProfile, BashTool, ToolInvocation
from pinser.runtime.tools_errors import ToolArgumentError, ToolExecutionError


def test_bash_tool_auto_allows_simple_read_only_command(tmp_path: Path) -> None:
    tool = BashTool(workspace_root=tmp_path)

    decision = tool.decide_permission(
        ToolInvocation(tool_name="Bash", arguments={"command": "pwd"})
    )

    assert decision.kind is PermissionDecisionKind.ALLOW


def test_bash_tool_requires_approval_for_compound_command(tmp_path: Path) -> None:
    tool = BashTool(workspace_root=tmp_path)

    decision = tool.decide_permission(
        ToolInvocation(tool_name="Bash", arguments={"command": "pwd && ls"})
    )

    assert decision.kind is PermissionDecisionKind.ASK
    assert decision.reason == "compound Bash commands require approval"


def test_bash_tool_denies_dangerous_program(tmp_path: Path) -> None:
    tool = BashTool(workspace_root=tmp_path)

    decision = tool.decide_permission(
        ToolInvocation(tool_name="Bash", arguments={"command": "sudo ls"})
    )

    assert decision.kind is PermissionDecisionKind.DENY
    assert decision.reason == "Bash command sudo is denied by policy"


def test_bash_tool_honors_rule_prefix_decisions(tmp_path: Path) -> None:
    tool = BashTool(
        workspace_root=tmp_path,
        permission_profile=BashPermissionProfile(
            denied_prefixes=("git push",),
            approval_required_prefixes=("git status",),
        ),
    )

    denied = tool.decide_permission(
        ToolInvocation(tool_name="Bash", arguments={"command": "git push origin main"})
    )
    asked = tool.decide_permission(
        ToolInvocation(tool_name="Bash", arguments={"command": "git status --short"})
    )

    assert denied.kind is PermissionDecisionKind.DENY
    assert denied.reason == "Bash command denied by rule: git push"
    assert asked.kind is PermissionDecisionKind.ASK
    assert asked.reason == "Bash command requires approval by rule: git status"


@pytest.mark.asyncio
async def test_bash_tool_executes_allowed_command(tmp_path: Path) -> None:
    tool = BashTool(workspace_root=tmp_path)

    result = await tool.execute(
        ToolInvocation(tool_name="Bash", arguments={"command": "printf 'hello'"})
    )

    assert result.output["stdout"] == "hello"
    assert result.output["stderr"] == ""
    assert result.output["returncode"] == 0
    assert result.output["content"] == "hello"


@pytest.mark.asyncio
async def test_bash_tool_rejects_background_execution_in_phase_2(tmp_path: Path) -> None:
    tool = BashTool(workspace_root=tmp_path)

    with pytest.raises(ToolArgumentError, match="background Bash execution is out of scope"):
        await tool.execute(
            ToolInvocation(
                tool_name="Bash",
                arguments={"command": "pwd", "run_in_background": True},
            )
        )


@pytest.mark.asyncio
async def test_bash_tool_rejects_sandbox_bypass_without_policy(tmp_path: Path) -> None:
    tool = BashTool(workspace_root=tmp_path)

    with pytest.raises(
        ToolExecutionError,
        match="dangerouslyDisableSandbox is not permitted by the current policy",
    ):
        await tool.execute(
            ToolInvocation(
                tool_name="Bash",
                arguments={"command": "pwd", "dangerouslyDisableSandbox": True},
            )
        )


@pytest.mark.asyncio
async def test_bash_tool_reports_nonzero_exit_for_allowed_read_only_command(
    tmp_path: Path,
) -> None:
    tool = BashTool(workspace_root=tmp_path)

    with pytest.raises(ToolExecutionError, match="command exited with status 2"):
        await tool.execute(
            ToolInvocation(
                tool_name="Bash",
                arguments={"command": "grep missing does-not-exist.txt"},
            )
        )


@pytest.mark.asyncio
async def test_bash_tool_reduces_environment_inheritance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PINSER_BASH_SECRET", "top-secret")
    monkeypatch.setenv("LANG", "C.UTF-8")
    tool = BashTool(
        workspace_root=tmp_path,
        permission_profile=BashPermissionProfile(auto_allow_read_only=False),
        allow_unsafe_testing_commands=True,
    )

    result = await tool.execute(
        ToolInvocation(
            tool_name="Bash",
            arguments={
                "command": (
                    f"{sys.executable} -c \"import os; "
                    "print(os.getenv('PINSER_BASH_SECRET', 'missing')); "
                    "print(os.getenv('LANG', 'missing'))\""
                )
            },
        )
    )

    assert result.output["stdout"] == "missing\nC.UTF-8\n"


@pytest.mark.asyncio
async def test_bash_tool_truncates_large_stdout(tmp_path: Path) -> None:
    tool = BashTool(
        workspace_root=tmp_path,
        permission_profile=BashPermissionProfile(auto_allow_read_only=False),
        allow_unsafe_testing_commands=True,
    )

    result = await tool.execute(
        ToolInvocation(
            tool_name="Bash",
            arguments={"command": f"{sys.executable} -c \"print('x' * 20000, end='')\""},
        )
    )

    assert len(result.output["stdout"]) == 16 * 1024
    assert result.output["stdout_truncated"] is True
    assert result.output["stderr_truncated"] is False
    assert "[output truncated to 16384 bytes per stream]" in result.output["content"]


@pytest.mark.asyncio
async def test_bash_tool_kills_process_group_on_timeout(tmp_path: Path) -> None:
    marker = tmp_path / "timeout-child-marker.txt"
    child_script = tmp_path / "child_timeout_writer.py"
    child_script.write_text(
        "import pathlib\n"
        "import sys\n"
        "import time\n"
        "marker = pathlib.Path(sys.argv[1])\n"
        "marker.write_text('started')\n"
        "time.sleep(5)\n",
        encoding="utf-8",
    )
    tool = BashTool(
        workspace_root=tmp_path,
        permission_profile=BashPermissionProfile(auto_allow_read_only=False),
        allow_unsafe_testing_commands=True,
    )

    command = (
        f"{sys.executable} -c \"import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, r'{child_script}', r'{marker}']); "
        "time.sleep(5)\""
    )

    with pytest.raises(ToolExecutionError, match=r"command timed out after 0\.2 seconds"):
        await tool.execute(
            ToolInvocation(
                tool_name="Bash",
                arguments={"command": command, "timeout": 0.2},
            )
        )

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not marker.exists():
        time.sleep(0.05)
    assert marker.exists()

    marker_mtime = marker.stat().st_mtime
    time.sleep(0.5)
    assert marker.stat().st_mtime == marker_mtime
