"""Protocol for model backends."""

from __future__ import annotations

from typing import Protocol


class ModelBackend(Protocol):
    """Backend capable of generating a reply for a user message."""

    async def generate(self, user_message: str) -> str:
        """Generate a response for the supplied user message."""
