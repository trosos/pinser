from __future__ import annotations

import asyncio

from pinser.runtime.conversation.messages import AssistantMessage, UserMessage
from pinser.runtime.engine.session import Session, SessionState
from pinser.runtime.events.models import EventType
from pinser.runtime.model.fake import FakeModel


async def test_session_streams_deterministic_events_in_order() -> None:
    session = Session(SessionState(session_id="session-1"), FakeModel())

    events = [event async for event in session.run_turn("hello")]

    assert [event.event_type for event in events] == [
        EventType.TURN_STARTED,
        EventType.ASSISTANT_MESSAGE,
        EventType.TURN_COMPLETED,
    ]
    assert session.state.turn_count == 1
    assert session.state.transcript == [
        UserMessage(content="hello"),
        AssistantMessage(content="Echo: hello"),
    ]


async def test_session_cancellation_before_model_output_keeps_state_unchanged() -> None:
    session = Session(SessionState(session_id="session-1"), FakeModel())
    cancellation_event = asyncio.Event()
    cancellation_event.set()

    events = [
        event
        async for event in session.run_turn(
            "hello",
            cancellation_event=cancellation_event,
        )
    ]

    assert [event.event_type for event in events] == [
        EventType.TURN_STARTED,
        EventType.TURN_CANCELLED,
    ]
    assert session.state.turn_count == 0
    assert session.state.transcript == []
