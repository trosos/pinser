"""Conservative Bash execution tool for the Phase 2 runtime."""

from __future__ import annotations

import asyncio
import contextlib
import os
import shlex
import signal
from dataclasses import dataclass, field
from pathlib import Path

from pinser.runtime.permissions import (
    PermissionDecision,
    PermissionDecisionKind,
    PermissionRequest,
)
from pinser.runtime.tools.protocol import ToolExecutionResult, ToolInvocation
from pinser.runtime.tools_errors import ToolArgumentError, ToolExecutionError

_READ_ONLY_COMMANDS = frozenset(
    {
        "cat",
        "echo",
        "find",
        "git",
        "grep",
        "head",
        "ls",
        "printf",
        "pwd",
        "rg",
        "sed",
        "sort",
        "tail",
        "wc",
        "which",
    }
)
_WRITE_COMMANDS = frozenset(
    {
        "chmod",
        "cp",
        "curl",
        "git",
        "install",
        "make",
        "mkdir",
        "mv",
        "npm",
        "pip",
        "python",
        "rm",
        "rmdir",
        "tee",
        "touch",
    }
)
_DENIED_COMMANDS = frozenset({"sudo", "su", "doas"})
_COMPOUND_OPERATORS = ("&&", "||", ";", "|")
_REDIRECTION_OPERATORS = (">",
    ">>",
    "1>",
    "1>>",
    "2>",
    "2>>",
    "&>",
    "&>>",
    "<",
    "<<",
)
_GIT_READ_ONLY_SUBCOMMANDS = frozenset(
    {"branch", "diff", "log", "rev-parse", "show", "status"}
)
_GIT_WRITE_SUBCOMMANDS = frozenset(
    {
        "add",
        "apply",
        "checkout",
        "cherry-pick",
        "clean",
        "commit",
        "merge",
        "pull",
        "push",
        "rebase",
        "reset",
        "restore",
        "stash",
        "switch",
        "tag",
    }
)
_BASH_OUTPUT_LIMIT = 16 * 1024
_BASH_ENV_ALLOWLIST = frozenset({"HOME", "LANG", "LC_ALL", "PATH", "PWD", "TERM", "TMPDIR"})
_TIMEOUT_KILL_GRACE_SECONDS = 1.0


@dataclass(frozen=True, slots=True)
class BashPermissionProfile:
    """Minimal Phase 2 policy knobs for Bash permission behavior."""

    auto_allow_read_only: bool = True
    allow_sandbox_bypass: bool = False
    denied_prefixes: tuple[str, ...] = ()
    approval_required_prefixes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BashAnalysis:
    """Structured analysis used for permission checks and execution routing."""

    summary: str
    program: str
    decision: PermissionDecision
    is_read_only: bool


@dataclass(frozen=True, slots=True)
class BashTool:
    """Foreground-only Bash tool with conservative command analysis."""

    workspace_root: Path
    permission_profile: BashPermissionProfile = field(default_factory=BashPermissionProfile)
    allow_unsafe_testing_commands: bool = False
    name: str = "Bash"

    def build_permission_request(self, invocation: ToolInvocation) -> PermissionRequest:
        command = self._require_command(invocation)
        return PermissionRequest(
            tool_name=self.name,
            summary=f"run bash: {command}",
            resource=str(self.workspace_root),
        )

    def decide_permission(self, invocation: ToolInvocation) -> PermissionDecision:
        return self._analyze(invocation).decision

    async def execute(self, invocation: ToolInvocation) -> ToolExecutionResult:
        command = self._require_command(invocation)
        timeout = self._require_timeout(invocation)
        run_in_background = self._require_run_in_background(invocation)
        dangerously_disable_sandbox = self._require_dangerously_disable_sandbox(invocation)

        if run_in_background:
            msg = "background Bash execution is out of scope for Phase 2"
            raise ToolArgumentError(msg)
        if dangerously_disable_sandbox and not self.permission_profile.allow_sandbox_bypass:
            msg = "dangerouslyDisableSandbox is not permitted by the current policy"
            raise ToolExecutionError(msg)

        analysis = self._analyze(invocation)
        if self.allow_unsafe_testing_commands:
            analysis = BashAnalysis(
                summary=analysis.summary,
                program=analysis.program,
                decision=PermissionDecision(kind=PermissionDecisionKind.ALLOW),
                is_read_only=analysis.is_read_only,
            )
        if analysis.decision.kind is PermissionDecisionKind.DENY:
            msg = analysis.decision.reason or "bash command denied"
            raise ToolExecutionError(msg)
        if analysis.decision.kind is PermissionDecisionKind.ASK:
            msg = analysis.decision.reason or "bash command requires approval"
            raise ToolExecutionError(msg)

        process = await asyncio.create_subprocess_exec(
            "/bin/bash",
            "-lc",
            command,
            cwd=self.workspace_root,
            env=self._build_environment(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
        except TimeoutError as exc:
            await self._terminate_process_group(process)
            msg = f"command timed out after {timeout} seconds"
            raise ToolExecutionError(msg) from exc

        stdout, stdout_truncated = self._decode_output(stdout_bytes)
        stderr, stderr_truncated = self._decode_output(stderr_bytes)
        if process.returncode != 0:
            msg = f"command exited with status {process.returncode}"
            if stderr.strip():
                msg = f"{msg}: {stderr.strip()}"
            raise ToolExecutionError(msg)

        result_summary = (
            stdout.strip()
            or stderr.strip()
            or f"command completed: {analysis.program}"
        )
        content = stdout.strip() or stderr.strip() or result_summary
        if stdout_truncated or stderr_truncated:
            content = f"{content}\n\n[output truncated to {_BASH_OUTPUT_LIMIT} bytes per stream]"
        return ToolExecutionResult(
            summary=result_summary,
            output={
                "command": command,
                "stdout": stdout,
                "stderr": stderr,
                "returncode": process.returncode,
                "content": content,
                "read_only": analysis.is_read_only,
                "stdout_truncated": stdout_truncated,
                "stderr_truncated": stderr_truncated,
            },
        )

    def _analyze(self, invocation: ToolInvocation) -> BashAnalysis:
        command = self._require_command(invocation)
        normalized = command.strip()
        if not normalized:
            msg = "Bash tool requires a non-empty string command argument."
            raise ToolArgumentError(msg)
        if any(operator in normalized for operator in _COMPOUND_OPERATORS):
            return BashAnalysis(
                summary=f"run bash: {normalized}",
                program="compound",
                decision=PermissionDecision(
                    kind=PermissionDecisionKind.ASK,
                    reason="compound Bash commands require approval",
                ),
                is_read_only=False,
            )
        if any(operator in normalized for operator in _REDIRECTION_OPERATORS):
            return BashAnalysis(
                summary=f"run bash: {normalized}",
                program="redirection",
                decision=PermissionDecision(
                    kind=PermissionDecisionKind.ASK,
                    reason="Bash redirections require approval",
                ),
                is_read_only=False,
            )
        if "$(" in normalized or "`" in normalized:
            return BashAnalysis(
                summary=f"run bash: {normalized}",
                program="substitution",
                decision=PermissionDecision(
                    kind=PermissionDecisionKind.ASK,
                    reason="Bash substitutions require approval",
                ),
                is_read_only=False,
            )

        tokens = self._split_command(normalized)
        program = Path(tokens[0]).name
        prefix_match = self._match_prefix(program, normalized)
        if prefix_match is not None:
            return BashAnalysis(
                summary=f"run bash: {normalized}",
                program=program,
                decision=prefix_match,
                is_read_only=False,
            )
        if program in _DENIED_COMMANDS:
            return BashAnalysis(
                summary=f"run bash: {normalized}",
                program=program,
                decision=PermissionDecision(
                    kind=PermissionDecisionKind.DENY,
                    reason=f"Bash command {program} is denied by policy",
                ),
                is_read_only=False,
            )

        read_only = self._is_read_only(tokens)
        if read_only and self.permission_profile.auto_allow_read_only:
            decision = PermissionDecision(kind=PermissionDecisionKind.ALLOW)
        else:
            decision = PermissionDecision(
                kind=PermissionDecisionKind.ASK,
                reason="Bash command requires approval",
            )
        return BashAnalysis(
            summary=f"run bash: {normalized}",
            program=program,
            decision=decision,
            is_read_only=read_only,
        )

    def _match_prefix(
        self, program: str, normalized_command: str
    ) -> PermissionDecision | None:
        for prefix in self.permission_profile.denied_prefixes:
            if normalized_command == prefix or normalized_command.startswith(f"{prefix} "):
                return PermissionDecision(
                    kind=PermissionDecisionKind.DENY,
                    reason=f"Bash command denied by rule: {prefix}",
                )
        for prefix in self.permission_profile.approval_required_prefixes:
            if normalized_command == prefix or normalized_command.startswith(f"{prefix} "):
                return PermissionDecision(
                    kind=PermissionDecisionKind.ASK,
                    reason=f"Bash command requires approval by rule: {prefix}",
                )
        if program == "cd":
            return PermissionDecision(
                kind=PermissionDecisionKind.ASK,
                reason="directory-changing Bash commands require approval",
            )
        return None

    def _is_read_only(self, tokens: list[str]) -> bool:
        program = Path(tokens[0]).name
        if program not in _READ_ONLY_COMMANDS:
            return False
        if any(token.startswith("-") and token in {"-i", "--in-place"} for token in tokens[1:]):
            return False
        if program == "git":
            if len(tokens) < 2:
                return False
            subcommand = tokens[1]
            if subcommand in _GIT_WRITE_SUBCOMMANDS:
                return False
            return subcommand in _GIT_READ_ONLY_SUBCOMMANDS
        if program == "echo":
            return all(not token.startswith("-") for token in tokens[1:])
        if program == "sed":
            return not any(token in {"-i", "--in-place"} for token in tokens[1:])
        if any(token in _WRITE_COMMANDS for token in tokens[1:]):
            return False
        return True

    def _build_environment(self) -> dict[str, str]:
        environment: dict[str, str] = {}
        for name in _BASH_ENV_ALLOWLIST:
            value = os.environ.get(name)
            if value is not None:
                environment[name] = value
        environment["PWD"] = str(self.workspace_root)
        environment.setdefault("PATH", os.defpath)
        return environment

    @staticmethod
    def _decode_output(data: bytes) -> tuple[str, bool]:
        truncated = len(data) > _BASH_OUTPUT_LIMIT
        limited = data[:_BASH_OUTPUT_LIMIT]
        return limited.decode(errors="replace"), truncated

    async def _terminate_process_group(
        self, process: asyncio.subprocess.Process
    ) -> None:
        if process.returncode is not None:
            return
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGTERM)
        try:
            await asyncio.wait_for(process.communicate(), timeout=_TIMEOUT_KILL_GRACE_SECONDS)
            return
        except TimeoutError:
            pass
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        await process.communicate()

    @staticmethod
    def _split_command(command: str) -> list[str]:
        try:
            tokens = shlex.split(command, posix=True)
        except ValueError as exc:
            msg = f"invalid Bash command syntax: {exc}"
            raise ToolArgumentError(msg) from exc
        if not tokens:
            msg = "Bash tool requires a non-empty string command argument."
            raise ToolArgumentError(msg)
        return tokens

    @staticmethod
    def _require_command(invocation: ToolInvocation) -> str:
        command = invocation.arguments.get("command")
        if not isinstance(command, str) or not command.strip():
            msg = "Bash tool requires a non-empty string command argument."
            raise ToolArgumentError(msg)
        return command

    @staticmethod
    def _require_timeout(invocation: ToolInvocation) -> float:
        timeout = invocation.arguments.get("timeout", 30)
        if isinstance(timeout, bool) or not isinstance(timeout, int | float) or timeout <= 0:
            msg = "Bash tool requires timeout to be a positive number when provided."
            raise ToolArgumentError(msg)
        return float(timeout)

    @staticmethod
    def _require_run_in_background(invocation: ToolInvocation) -> bool:
        value = invocation.arguments.get("run_in_background", False)
        if not isinstance(value, bool):
            msg = "Bash tool requires run_in_background to be a boolean when provided."
            raise ToolArgumentError(msg)
        return value

    @staticmethod
    def _require_dangerously_disable_sandbox(invocation: ToolInvocation) -> bool:
        value = invocation.arguments.get("dangerouslyDisableSandbox", False)
        if not isinstance(value, bool):
            msg = (
                "Bash tool requires dangerouslyDisableSandbox to be a boolean when provided."
            )
            raise ToolArgumentError(msg)
        return value
