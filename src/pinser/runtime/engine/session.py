"""Session and turn execution primitives for Phase 1."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from pinser.runtime.context.prompt import PromptContext, build_prompt_context
from pinser.runtime.conversation.messages import AssistantMessage, ConversationItem, UserMessage
from pinser.runtime.events.models import (
    AssistantMessageEvent,
    Event,
    ProgressEvent,
    TurnCancelledEvent,
    TurnCompletedEvent,
    TurnStartedEvent,
    UserMessageEvent,
)
from pinser.runtime.model.protocol import ModelBackend


@dataclass(frozen=True, slots=True)
class TurnState:
    """Per-turn derived state used during execution."""

    turn_id: int
    user_message: str
    prompt_context: PromptContext


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

    def prepare_turn(self, user_message: str) -> TurnState:
        """Build explicit per-turn state before model execution."""

        return TurnState(
            turn_id=self._state.turn_count + 1,
            user_message=user_message,
            prompt_context=build_prompt_context(self._state, user_message),
        )

    async def run_turn(
        self,
        user_message: str,
        *,
        cancellation_event: asyncio.Event | None = None,
    ) -> AsyncIterator[Event]:
        """Execute one turn and stream ordered runtime events."""

        turn_state = self.prepare_turn(user_message)
        yield TurnStartedEvent(
            session_id=self._state.session_id,
            turn_id=turn_state.turn_id,
            user_message=turn_state.user_message,
        )
        yield UserMessageEvent(
            session_id=self._state.session_id,
            turn_id=turn_state.turn_id,
            message=turn_state.user_message,
        )

        if cancellation_event is not None and cancellation_event.is_set():
            yield TurnCancelledEvent(
                session_id=self._state.session_id,
                turn_id=turn_state.turn_id,
            )
            return

        yield ProgressEvent(
            session_id=self._state.session_id,
            turn_id=turn_state.turn_id,
            stage="generating",
        )
        assistant_message = await self._model.generate(turn_state.prompt_context)
        yield AssistantMessageEvent(
            session_id=self._state.session_id,
            turn_id=turn_state.turn_id,
            message=assistant_message,
        )

        if cancellation_event is not None and cancellation_event.is_set():
            yield TurnCancelledEvent(
                session_id=self._state.session_id,
                turn_id=turn_state.turn_id,
            )
            return

        self._state.turn_count = turn_state.turn_id
        self._state.transcript.extend(
            (
                UserMessage(content=turn_state.user_message),
                AssistantMessage(content=assistant_message),
            )
        )
        yield TurnCompletedEvent(
            session_id=self._state.session_id,
            turn_id=turn_state.turn_id,
        )
