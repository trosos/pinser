from dataclasses import dataclass
from pathlib import Path

import pytest
from support_models import SequenceModel

from pinser.runtime.engine.session import Session, SessionState
from pinser.runtime.events.models import PermissionRequiredEvent, ToolDeniedEvent
from pinser.runtime.model.messages import AssistantStep, ToolCall
from pinser.runtime.tools import BashTool, ToolRegistry


@dataclass(frozen=True, slots=True)
class WorkerLaunchRequest:
    worker_name: str
    permission_mode: str
    tool_names: tuple[str, ...]


def spawn_worker_registry(
    *,
    parent_registry: ToolRegistry,
    request: WorkerLaunchRequest,
) -> ToolRegistry:
    if request.permission_mode != "dontAsk":
        msg = "worker launch must preserve dontAsk permission mode"
        raise PermissionError(msg)
    if request.tool_names != parent_registry.names():
        msg = "worker launch must preserve parent tool visibility"
        raise PermissionError(msg)

    worker_registry = ToolRegistry()
    for tool_name in request.tool_names:
        tool = parent_registry.get(tool_name)
        if tool is None:
            msg = f"worker launch referenced unavailable tool {tool_name}"
            raise PermissionError(msg)
        worker_registry.register(tool)
    return worker_registry


def terminate_worker_registry(*, active_tasks: set[str]) -> None:
    if active_tasks:
        msg = "cannot terminate worker with active background tasks"
        raise PermissionError(msg)


@pytest.mark.asyncio
async def test_worker_spawn_preserves_parent_permission_mode_and_tool_visibility(
    tmp_path: Path,
) -> None:
    parent_registry = ToolRegistry()
    parent_registry.register(BashTool(workspace_root=tmp_path))
    worker_registry = spawn_worker_registry(
        parent_registry=parent_registry,
        request=WorkerLaunchRequest(
            worker_name="worker-1",
            permission_mode="dontAsk",
            tool_names=parent_registry.names(),
        ),
    )
    model = SequenceModel(
        responses=[
            AssistantStep(
                tool_call=ToolCall(tool_name="Bash", arguments={"command": "mkdir child-build"})
            )
        ]
    )
    session = Session(
        SessionState(session_id="worker-session", workspace_root=tmp_path),
        model,
        workspace_root=tmp_path,
        tools=worker_registry,
    )

    events = [event async for event in session.run_turn("spawned worker tries to write")]

    assert isinstance(events[4], PermissionRequiredEvent)
    assert events[4].summary == "run bash: mkdir child-build"
    assert isinstance(events[5], ToolDeniedEvent)
    assert events[5].reason == "approval-required action blocked by dontAsk mode."


def test_worker_spawn_rejects_broader_tool_visibility_than_parent(tmp_path: Path) -> None:
    parent_registry = ToolRegistry()
    parent_registry.register(BashTool(workspace_root=tmp_path))

    with pytest.raises(PermissionError, match="preserve parent tool visibility"):
        spawn_worker_registry(
            parent_registry=parent_registry,
            request=WorkerLaunchRequest(
                worker_name="worker-2",
                permission_mode="dontAsk",
                tool_names=("Bash", "RemoteTrigger"),
            ),
        )


def test_worker_termination_rejects_active_background_tasks() -> None:
    with pytest.raises(PermissionError, match="active background tasks"):
        terminate_worker_registry(active_tasks={"task-1"})


def test_worker_termination_allows_clean_shutdown_without_active_tasks() -> None:
    terminate_worker_registry(active_tasks=set())
