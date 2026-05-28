"""Test helpers for deterministic model backends."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from pinser.runtime.context.prompt import PromptContext
from pinser.runtime.model.messages import AssistantStep
from pinser.runtime.model.protocol import ModelBackend


@dataclass(slots=True)
class SequenceModel(ModelBackend):
    """Return a predefined sequence of model outputs."""

    responses: Sequence[AssistantStep]
    prompts: list[PromptContext] = field(default_factory=list)
    _index: int = 0

    async def generate(self, prompt_context: PromptContext) -> AssistantStep:
        self.prompts.append(prompt_context)
        if self._index >= len(self.responses):
            msg = "SequenceModel has no remaining responses."
            raise AssertionError(msg)

        response = self.responses[self._index]
        self._index += 1
        return response
