"""Fake model backend for tests and bootstrap runtime behavior."""

from __future__ import annotations

from pinser.runtime.context.prompt import PromptContext
from pinser.runtime.model.messages import AssistantStep


class FakeModel:
    """Simple deterministic backend used for Phase 1 tests."""

    async def generate(self, prompt_context: PromptContext) -> AssistantStep:
        latest_user_message = prompt_context.messages[-1].content.strip()
        return AssistantStep(message=f"Echo: {latest_user_message}")
