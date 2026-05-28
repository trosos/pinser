"""Typed in-memory conversation messages."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UserMessage:
    """User-authored message stored in session transcript."""

    content: str


@dataclass(frozen=True, slots=True)
class AssistantMessage:
    """Assistant-authored message stored in session transcript."""

    content: str


@dataclass(frozen=True, slots=True)
class ToolResultMessage:
    """Tool result stored explicitly for future prompt normalization work."""

    tool_name: str
    content: str
    is_error: bool = False


type ConversationItem = UserMessage | AssistantMessage | ToolResultMessage
