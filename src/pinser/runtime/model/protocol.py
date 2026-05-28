"""Protocol for model backends."""

from __future__ import annotations

from typing import Protocol

from pinser.runtime.context.prompt import PromptContext
from pinser.runtime.model.messages import AssistantStep


class ModelBackend(Protocol):
    """Backend capable of generating a reply for a prepared prompt context."""

    async def generate(self, prompt_context: PromptContext) -> AssistantStep:
        """Generate a response for the supplied prompt context."""
