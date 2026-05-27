"""Typed runtime events for Phase 1."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EventType(StrEnum):
    """Kinds of events the runtime can emit during a turn."""

    TURN_STARTED = "turn_started"
    USER_MESSAGE = "user_message"
    PROGRESS = "progress"
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
    | AssistantMessageEvent
    | TurnCompletedEvent
    | TurnCancelledEvent
)
