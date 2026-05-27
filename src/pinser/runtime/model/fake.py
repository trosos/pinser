"""Fake model backend for tests and bootstrap runtime behavior."""

from __future__ import annotations


class FakeModel:
    """Simple deterministic backend used for Phase 1 tests."""

    async def generate(self, user_message: str) -> str:
        normalized_message = user_message.strip()
        return f"Echo: {normalized_message}"
