"""Registry for Phase 2 tools."""

from __future__ import annotations

from dataclasses import dataclass, field

from pinser.runtime.tools.protocol import Tool


@dataclass(slots=True)
class ToolRegistry:
    """Simple in-memory registry keyed by stable tool name."""

    _tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, tool_name: str) -> Tool | None:
        return self._tools.get(tool_name)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))
