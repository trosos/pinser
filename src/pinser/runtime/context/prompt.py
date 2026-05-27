"""Prompt assembly primitives for the runtime."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from pinser.runtime.conversation.messages import AssistantMessage, ConversationItem, UserMessage


class SessionView(Protocol):
    """Readonly session shape needed by prompt assembly."""

    session_id: str
    turn_count: int
    transcript: list[ConversationItem]


class PromptRole(StrEnum):
    """Role of a message in prompt assembly."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class PromptMessage:
    """One normalized message included in model context."""

    role: PromptRole
    content: str


@dataclass(frozen=True, slots=True)
class PromptContext:
    """Structured prompt context delivered to a model backend."""

    session_id: str
    turn_id: int
    messages: tuple[PromptMessage, ...]


SYSTEM_PROMPT = (
    "You are Pinser, a local-first coding assistant bootstrap runtime. "
    "Be concise and deterministic."
)


def _prompt_message_for_item(item: ConversationItem) -> PromptMessage:
    if isinstance(item, UserMessage):
        return PromptMessage(role=PromptRole.USER, content=item.content)
    if isinstance(item, AssistantMessage):
        return PromptMessage(role=PromptRole.ASSISTANT, content=item.content)
    msg = f"Unsupported conversation item: {type(item)!r}"
    raise TypeError(msg)


def build_prompt_context(session_state: SessionView, user_message: str) -> PromptContext:
    """Build the minimal structured prompt context for a turn."""

    messages: list[PromptMessage] = [PromptMessage(role=PromptRole.SYSTEM, content=SYSTEM_PROMPT)]

    for transcript_entry in session_state.transcript:
        messages.append(_prompt_message_for_item(transcript_entry))

    messages.append(PromptMessage(role=PromptRole.USER, content=user_message))

    return PromptContext(
        session_id=session_state.session_id,
        turn_id=session_state.turn_count + 1,
        messages=tuple(messages),
    )
