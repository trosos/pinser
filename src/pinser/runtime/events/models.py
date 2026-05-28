"""Typed runtime events for Phase 2."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pinser.runtime.permissions import PermissionDecisionKind


class EventType(StrEnum):
    """Kinds of events the runtime can emit during a turn."""

    TURN_STARTED = "turn_started"
    USER_MESSAGE = "user_message"
    PROGRESS = "progress"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    PERMISSION_REQUIRED = "permission_required"
    TOOL_DENIED = "tool_denied"
    TOOL_BLOCKED = "tool_blocked"
    TOOL_FAILED = "tool_failed"
    ASSISTANT_MESSAGE = "assistant_message"
    TURN_COMPLETED = "turn_completed"
    TURN_CANCELLED = "turn_cancelled"


@dataclass(frozen=True, slots=True)
class TurnStartedEvent:
    """Signals that a turn has started execution."""

    session_id: str
    turn_id: int
    user_message: str
    event_type: EventType = EventType.TURN_STARTED


@dataclass(frozen=True, slots=True)
class UserMessageEvent:
    """Represents user input as conversation content for the current turn."""

    session_id: str
    turn_id: int
    message: str
    event_type: EventType = EventType.USER_MESSAGE


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    """Represents ephemeral runtime progress that is not added to transcript state."""

    session_id: str
    turn_id: int
    stage: str
    event_type: EventType = EventType.PROGRESS


@dataclass(frozen=True, slots=True)
class ToolStartedEvent:
    """Signals that a tool invocation has started."""

    session_id: str
    turn_id: int
    tool_name: str
    summary: str
    event_type: EventType = EventType.TOOL_STARTED


@dataclass(frozen=True, slots=True)
class ToolCompletedEvent:
    """Signals that a tool invocation completed successfully."""

    session_id: str
    turn_id: int
    tool_name: str
    summary: str
    event_type: EventType = EventType.TOOL_COMPLETED


@dataclass(frozen=True, slots=True)
class PermissionRequiredEvent:
    """Signals that a tool action requires user approval."""

    session_id: str
    turn_id: int
    tool_name: str
    summary: str
    resource: str | None = None
    event_type: EventType = EventType.PERMISSION_REQUIRED


@dataclass(frozen=True, slots=True)
class ToolDeniedEvent:
    """Signals that a tool action was denied by permission policy."""

    session_id: str
    turn_id: int
    tool_name: str
    decision: PermissionDecisionKind
    reason: str
    event_type: EventType = EventType.TOOL_DENIED


@dataclass(frozen=True, slots=True)
class ToolBlockedEvent:
    """Signals that a tool action was blocked by a local safety invariant."""

    session_id: str
    turn_id: int
    tool_name: str
    reason: str
    event_type: EventType = EventType.TOOL_BLOCKED


@dataclass(frozen=True, slots=True)
class ToolFailedEvent:
    """Signals that a tool action failed after attempting execution."""

    session_id: str
    turn_id: int
    tool_name: str
    reason: str
    event_type: EventType = EventType.TOOL_FAILED


@dataclass(frozen=True, slots=True)
class AssistantMessageEvent:
    """Represents assistant output produced during a turn."""

    session_id: str
    turn_id: int
    message: str
    event_type: EventType = EventType.ASSISTANT_MESSAGE


@dataclass(frozen=True, slots=True)
class TurnCompletedEvent:
    """Signals that a turn completed successfully."""

    session_id: str
    turn_id: int
    event_type: EventType = EventType.TURN_COMPLETED


@dataclass(frozen=True, slots=True)
class TurnCancelledEvent:
    """Signals that a turn was cancelled before completion."""

    session_id: str
    turn_id: int
    reason: str = "cancelled"
    event_type: EventType = EventType.TURN_CANCELLED


type Event = (
    TurnStartedEvent
    | UserMessageEvent
    | ProgressEvent
    | ToolStartedEvent
    | ToolCompletedEvent
    | PermissionRequiredEvent
    | ToolDeniedEvent
    | ToolBlockedEvent
    | ToolFailedEvent
    | AssistantMessageEvent
    | TurnCompletedEvent
    | TurnCancelledEvent
)
