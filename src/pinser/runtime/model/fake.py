"""Fake model backend for tests and bootstrap runtime behavior."""

from __future__ import annotations

from pinser.runtime.context.prompt import PromptContext


class FakeModel:
    """Simple deterministic backend used for Phase 1 tests."""

    async def generate(self, prompt_context: PromptContext) -> str:
        latest_user_message = prompt_context.messages[-1].content.strip()
        return f"Echo: {latest_user_message}"
