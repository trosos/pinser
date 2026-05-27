"""Headless runtime facade for driving a session turn."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from pinser.runtime.engine.session import Session, SessionState
from pinser.runtime.events.models import Event
from pinser.runtime.model.fake import FakeModel
from pinser.runtime.model.protocol import ModelBackend


@dataclass(slots=True)
class Runtime:
    """Tiny headless runtime facade around an in-memory session."""

    session: Session

    @classmethod
    def create(
        cls,
        *,
        model: ModelBackend | None = None,
        session_id: str | None = None,
    ) -> Runtime:
        """Create a runtime with default in-memory state and model."""

        return cls(
            session=Session(
                SessionState(session_id=session_id or str(uuid4())),
                model or FakeModel(),
            )
        )

    async def run_turn(self, user_message: str) -> list[Event]:
        """Execute one turn and collect its streamed events."""

        return [event async for event in self.session.run_turn(user_message)]
