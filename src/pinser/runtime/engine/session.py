"""Session and turn execution primitives for Phase 1."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from pinser.runtime.context.prompt import build_prompt_context
from pinser.runtime.conversation.messages import AssistantMessage, ConversationItem, UserMessage
from pinser.runtime.events.models import (
    AssistantMessageEvent,
    Event,
    TurnCancelledEvent,
    TurnCompletedEvent,
    TurnStartedEvent,
)
from pinser.runtime.model.protocol import ModelBackend


@dataclass(slots=True)
class SessionState:
    """Conversation state that persists across turns in memory."""

    session_id: str
    turn_count: int = 0
    transcript: list[ConversationItem] = field(default_factory=list)


class Session:
    """Minimal conversation session with async event streaming."""

    def __init__(self, state: SessionState, model: ModelBackend) -> None:
        self._state = state
        self._model = model

    @property
    def state(self) -> SessionState:
        """Return the persistent session state."""

        return self._state

    async def run_turn(
        self,
        user_message: str,
        *,
        cancellation_event: asyncio.Event | None = None,
    ) -> AsyncIterator[Event]:
        """Execute one turn and stream ordered runtime events."""

        next_turn_id = self._state.turn_count + 1
        started_event = TurnStartedEvent(
            session_id=self._state.session_id,
            turn_id=next_turn_id,
            user_message=user_message,
        )
        yield started_event

        if cancellation_event is not None and cancellation_event.is_set():
            yield TurnCancelledEvent(
                session_id=self._state.session_id,
                turn_id=next_turn_id,
            )
            return

        prompt_context = build_prompt_context(self._state, user_message)
        assistant_message = await self._model.generate(prompt_context)
        message_event = AssistantMessageEvent(
            session_id=self._state.session_id,
            turn_id=next_turn_id,
            message=assistant_message,
        )
        yield message_event

        if cancellation_event is not None and cancellation_event.is_set():
            yield TurnCancelledEvent(
                session_id=self._state.session_id,
                turn_id=next_turn_id,
            )
            return

        self._state.turn_count = next_turn_id
        self._state.transcript.extend(
            (
                UserMessage(content=user_message),
                AssistantMessage(content=assistant_message),
            )
        )
        yield TurnCompletedEvent(
            session_id=self._state.session_id,
            turn_id=next_turn_id,
        )
