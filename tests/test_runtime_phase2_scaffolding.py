from typing import cast

from pinser.runtime.permissions import (
    PermissionDecision,
    PermissionDecisionKind,
    PermissionRequest,
)
from pinser.runtime.tools import ToolExecutionResult, ToolInvocation, ToolRegistry


def test_permission_decision_helpers_reflect_decision_kind() -> None:
    decision = PermissionDecision(
        kind=PermissionDecisionKind.ASK,
        reason="approval required",
    )

    assert not decision.is_allow
    assert decision.is_ask
    assert not decision.is_deny


def test_tool_registry_registers_and_lists_tools() -> None:
    class DummyTool:
        name = "Read"

        def build_permission_request(self, invocation: ToolInvocation) -> PermissionRequest:
            return PermissionRequest(tool_name=self.name, summary="read file")

        def decide_permission(self, invocation: ToolInvocation) -> PermissionDecision:
            return PermissionDecision(kind=PermissionDecisionKind.ALLOW)

        async def execute(
            self, invocation: ToolInvocation
        ) -> ToolExecutionResult:  # pragma: no cover - scaffold only
            raise NotImplementedError

    registry = ToolRegistry()
    tool = DummyTool()

    registry.register(tool)

    registered_tool = cast(DummyTool, registry.get("Read"))
    assert registered_tool is tool
    assert registry.get("Missing") is None
    assert registry.names() == ("Read",)
