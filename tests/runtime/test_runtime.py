from __future__ import annotations

from pinser.runtime.engine import Runtime
from pinser.runtime.events.models import EventType
from pinser.runtime.model.fake import FakeModel


async def test_runtime_collects_turn_events_and_updates_session_state() -> None:
    runtime = Runtime.create(model=FakeModel(), session_id="session-1")

    events = await runtime.run_turn("hello")

    assert [event.event_type for event in events] == [
        EventType.TURN_STARTED,
        EventType.USER_MESSAGE,
        EventType.PROGRESS,
        EventType.ASSISTANT_MESSAGE,
        EventType.TURN_COMPLETED,
    ]
    assert runtime.session.state.session_id == "session-1"
    assert runtime.session.state.turn_count == 1
