"""Permission decision models for Phase 2 runtime scaffolding."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PermissionDecisionKind(StrEnum):
    """Normalized permission outcomes used by the runtime."""

    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class PermissionDecision:
    """A normalized permission decision with optional human-readable reason."""

    kind: PermissionDecisionKind
    reason: str | None = None

    @property
    def is_allow(self) -> bool:
        return self.kind is PermissionDecisionKind.ALLOW

    @property
    def is_ask(self) -> bool:
        return self.kind is PermissionDecisionKind.ASK

    @property
    def is_deny(self) -> bool:
        return self.kind is PermissionDecisionKind.DENY


@dataclass(frozen=True, slots=True)
class PermissionRequest:
    """Structured permission request data for a pending tool action."""

    tool_name: str
    summary: str
    resource: str | None = None
