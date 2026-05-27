"""Protocol for model backends."""

from __future__ import annotations

from typing import Protocol

from pinser.runtime.context.prompt import PromptContext


class ModelBackend(Protocol):
    """Backend capable of generating a reply for a prepared prompt context."""

    async def generate(self, prompt_context: PromptContext) -> str:
        """Generate a response for the supplied prompt context."""
