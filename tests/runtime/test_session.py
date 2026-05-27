from __future__ import annotations

import asyncio

from pinser.runtime.context.prompt import PromptRole
from pinser.runtime.conversation.messages import AssistantMessage, UserMessage
from pinser.runtime.engine.session import Session, SessionState
from pinser.runtime.events.models import EventType
from pinser.runtime.model.fake import FakeModel


def test_prepare_turn_builds_explicit_turn_state() -> None:
    session = Session(
        SessionState(
            session_id="session-1",
            turn_count=1,
            transcript=[UserMessage(content="hello"), AssistantMessage(content="Echo: hello")],
        ),
        FakeModel(),
    )

    turn_state = session.prepare_turn("what next?")

    assert turn_state.turn_id == 2
    assert turn_state.user_message == "what next?"
    assert [message.role for message in turn_state.prompt_context.messages] == [
        PromptRole.SYSTEM,
        PromptRole.USER,
        PromptRole.ASSISTANT,
        PromptRole.USER,
    ]
    assert turn_state.prompt_context.messages[-1].content == "what next?"


async def test_session_streams_deterministic_events_in_order() -> None:
    session = Session(SessionState(session_id="session-1"), FakeModel())

    events = [event async for event in session.run_turn("hello")]

    assert [event.event_type for event in events] == [
        EventType.TURN_STARTED,
        EventType.USER_MESSAGE,
        EventType.PROGRESS,
        EventType.ASSISTANT_MESSAGE,
        EventType.TURN_COMPLETED,
    ]
    assert session.state.turn_count == 1
    assert session.state.transcript == [
        UserMessage(content="hello"),
        AssistantMessage(content="Echo: hello"),
    ]


async def test_progress_event_does_not_alter_transcript_state() -> None:
    session = Session(SessionState(session_id="session-1"), FakeModel())

    events = [event async for event in session.run_turn("hello")]
    progress_event = events[2]

    assert progress_event.event_type == EventType.PROGRESS
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
        EventType.USER_MESSAGE,
        EventType.TURN_CANCELLED,
    ]
    assert session.state.turn_count == 0
    assert session.state.transcript == []
