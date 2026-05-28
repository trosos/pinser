"""Structured tool/runtime error types for Phase 2 execution."""

from __future__ import annotations


class ToolExecutionError(Exception):
    """Base class for runtime-visible tool execution failures."""


class ToolPermissionDeniedError(ToolExecutionError):
    """Tool invocation was denied by runtime policy or permissions."""


class ToolSafetyBlockedError(ToolExecutionError):
    """Tool invocation was blocked by a safety invariant."""


class ToolArgumentError(ToolExecutionError):
    """Tool invocation arguments are invalid."""
